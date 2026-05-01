from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Literal

import torch
import torch.nn as nn
import torch.nn.functional as F
from ultralytics.models.yolo.detect.train import DetectionTrainer
from ultralytics.nn import tasks
from ultralytics.nn.modules.block import C2f as UltralyticsC2f
from ultralytics.utils import loss as yolo_loss
from ultralytics.utils.metrics import bbox_iou
from ultralytics.utils.tal import bbox2dist

LossName = Literal["ciou", "piou", "innermpdiou"]

_ORIGINAL_C2F = tasks.C2f
_ORIGINAL_BBOXLOSS_FORWARD = yolo_loss.BboxLoss.forward
_PATCHED = False


class SimAM(nn.Module):
    """Parameter-free 3D attention (SimAM)."""

    def __init__(self, e_lambda: float = 1e-4):
        super().__init__()
        self.e_lambda = e_lambda

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        b, c, h, w = x.shape
        n = max(h * w - 1, 1)
        d = (x - x.mean(dim=(2, 3), keepdim=True)).pow(2)
        v = d.sum(dim=(2, 3), keepdim=True) / n
        e_inv = d / (4 * (v + self.e_lambda)) + 0.5
        return x * torch.sigmoid(e_inv)


class EMAModule(nn.Module):
    """Efficient multi-scale attention block (lightweight local+global fusion)."""

    def __init__(self, channels: int, reduction: int = 16):
        super().__init__()
        hidden = max(channels // reduction, 8)
        self.dw3 = nn.Conv2d(channels, channels, kernel_size=3, padding=1, groups=channels, bias=False)
        self.dw5 = nn.Conv2d(channels, channels, kernel_size=5, padding=2, groups=channels, bias=False)
        self.pw = nn.Conv2d(channels, channels, kernel_size=1, bias=False)
        self.avg = nn.AdaptiveAvgPool2d(1)
        self.fc = nn.Sequential(
            nn.Conv2d(channels, hidden, kernel_size=1, bias=True),
            nn.SiLU(inplace=True),
            nn.Conv2d(hidden, channels, kernel_size=1, bias=True),
            nn.Sigmoid(),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        local = self.dw3(x) + self.dw5(x)
        global_gate = self.fc(self.avg(x))
        fused = local + (x * global_gate)
        return self.pw(fused)


class C2fSimAMEMA(UltralyticsC2f):
    """Drop-in C2f replacement with SimAM + EMA attention."""

    def __init__(self, c1: int, c2: int, n: int = 1, shortcut: bool = False, g: int = 1, e: float = 0.5):
        super().__init__(c1, c2, n=n, shortcut=shortcut, g=g, e=e)
        self.simam = SimAM()
        self.ema = EMAModule(c2)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = super().forward(x)
        x = self.simam(x)
        x = self.ema(x)
        return x


def _piou_quality(pred_xyxy: torch.Tensor, gt_xyxy: torch.Tensor, eps: float = 1e-7) -> torch.Tensor:
    iou = bbox_iou(pred_xyxy, gt_xyxy, xywh=False).clamp(min=-1.0, max=1.0)
    px1, py1, px2, py2 = pred_xyxy.chunk(4, dim=-1)
    gx1, gy1, gx2, gy2 = gt_xyxy.chunk(4, dim=-1)
    gw = (gx2 - gx1).clamp_min(eps)
    gh = (gy2 - gy1).clamp_min(eps)
    p_term = (
        (px1 - gx1).abs() / gw
        + (px2 - gx2).abs() / gw
        + (py1 - gy1).abs() / gh
        + (py2 - gy2).abs() / gh
    ) / 4.0
    penalty = 1.0 - torch.exp(-(p_term**2))
    return (iou - penalty).clamp(min=-1.0, max=1.0)


def _inner_iou(pred_xyxy: torch.Tensor, gt_xyxy: torch.Tensor, ratio: float = 0.8, eps: float = 1e-7) -> torch.Tensor:
    px1, py1, px2, py2 = pred_xyxy.chunk(4, dim=-1)
    gx1, gy1, gx2, gy2 = gt_xyxy.chunk(4, dim=-1)

    pw = (px2 - px1).clamp_min(eps)
    ph = (py2 - py1).clamp_min(eps)
    gw = (gx2 - gx1).clamp_min(eps)
    gh = (gy2 - gy1).clamp_min(eps)

    pcx, pcy = (px1 + px2) * 0.5, (py1 + py2) * 0.5
    gcx, gcy = (gx1 + gx2) * 0.5, (gy1 + gy2) * 0.5

    ipx1, ipx2 = pcx - pw * ratio * 0.5, pcx + pw * ratio * 0.5
    ipy1, ipy2 = pcy - ph * ratio * 0.5, pcy + ph * ratio * 0.5
    igx1, igx2 = gcx - gw * ratio * 0.5, gcx + gw * ratio * 0.5
    igy1, igy2 = gcy - gh * ratio * 0.5, gcy + gh * ratio * 0.5

    inter_w = (torch.minimum(ipx2, igx2) - torch.maximum(ipx1, igx1)).clamp(min=0.0)
    inter_h = (torch.minimum(ipy2, igy2) - torch.maximum(ipy1, igy1)).clamp(min=0.0)
    inter = inter_w * inter_h
    union = (pw * ph * ratio * ratio) + (gw * gh * ratio * ratio) - inter + eps
    return inter / union


def _innermpdiou_quality(pred_xyxy: torch.Tensor, gt_xyxy: torch.Tensor, eps: float = 1e-7) -> torch.Tensor:
    iou = bbox_iou(pred_xyxy, gt_xyxy, xywh=False).clamp(min=-1.0, max=1.0)
    d1 = ((pred_xyxy[:, 0:1] - gt_xyxy[:, 0:1]) ** 2) + ((pred_xyxy[:, 1:2] - gt_xyxy[:, 1:2]) ** 2)
    d2 = ((pred_xyxy[:, 2:3] - gt_xyxy[:, 2:3]) ** 2) + ((pred_xyxy[:, 3:4] - gt_xyxy[:, 3:4]) ** 2)
    gw = (gt_xyxy[:, 2:3] - gt_xyxy[:, 0:1]).clamp_min(eps)
    gh = (gt_xyxy[:, 3:4] - gt_xyxy[:, 1:2]).clamp_min(eps)
    mpdiou = iou - (d1 + d2) / (gw * gw + gh * gh + eps)
    inner = _inner_iou(pred_xyxy, gt_xyxy, ratio=0.8, eps=eps)
    loss = (1.0 - mpdiou) + (iou - inner)
    return (1.0 - loss).clamp(min=-1.0, max=1.0)


def _patched_bboxloss_forward(
    self,
    pred_dist: torch.Tensor,
    pred_bboxes: torch.Tensor,
    anchor_points: torch.Tensor,
    target_bboxes: torch.Tensor,
    target_scores: torch.Tensor,
    target_scores_sum: torch.Tensor,
    fg_mask: torch.Tensor,
    imgsz: torch.Tensor,
    stride: torch.Tensor,
) -> tuple[torch.Tensor, torch.Tensor]:
    weight = target_scores.sum(-1)[fg_mask].unsqueeze(-1)
    if pred_bboxes[fg_mask].shape[0] == 0:
        zero = pred_dist.sum() * 0.0
        return zero, zero

    mode = getattr(self, "_bbox_loss_mode", "ciou")
    pred_fg = pred_bboxes[fg_mask]
    tgt_fg = target_bboxes[fg_mask]
    if mode == "piou":
        quality = _piou_quality(pred_fg, tgt_fg)
    elif mode == "innermpdiou":
        quality = _innermpdiou_quality(pred_fg, tgt_fg)
    else:
        quality = bbox_iou(pred_fg, tgt_fg, xywh=False, CIoU=True)

    loss_iou = ((1.0 - quality) * weight).sum() / target_scores_sum

    if self.dfl_loss:
        target_ltrb = bbox2dist(anchor_points, target_bboxes, self.dfl_loss.reg_max - 1)
        loss_dfl = self.dfl_loss(pred_dist[fg_mask].view(-1, self.dfl_loss.reg_max), target_ltrb[fg_mask]) * weight
        loss_dfl = loss_dfl.sum() / target_scores_sum
    else:
        target_ltrb = bbox2dist(anchor_points, target_bboxes)
        target_ltrb = target_ltrb * stride
        target_ltrb[..., 0::2] /= imgsz[1]
        target_ltrb[..., 1::2] /= imgsz[0]
        pred_dist = pred_dist * stride
        pred_dist[..., 0::2] /= imgsz[1]
        pred_dist[..., 1::2] /= imgsz[0]
        loss_dfl = (
            F.l1_loss(pred_dist[fg_mask], target_ltrb[fg_mask], reduction="none").mean(-1, keepdim=True) * weight
        )
        loss_dfl = loss_dfl.sum() / target_scores_sum
    return loss_iou, loss_dfl


@dataclass
class BlurConfig:
    prob: float = 0.5
    sigma_min: float = 0.5
    sigma_max: float = 2.5


def _gaussian_kernel2d(sigma: float, device: torch.device, dtype: torch.dtype) -> torch.Tensor:
    k = int(max(3, math.ceil(6.0 * sigma)))
    if k % 2 == 0:
        k += 1
    x = torch.arange(k, device=device, dtype=dtype) - (k // 2)
    g1 = torch.exp(-0.5 * (x / sigma) ** 2)
    g1 = g1 / g1.sum()
    g2 = torch.outer(g1, g1)
    return g2 / g2.sum()


def apply_random_gaussian_blur(imgs: torch.Tensor, cfg: BlurConfig) -> torch.Tensor:
    """Apply per-image Gaussian blur with sigma sampled from U(sigma_min, sigma_max)."""
    if imgs.ndim != 4:
        return imgs
    b, c, _, _ = imgs.shape
    for i in range(b):
        if random.random() > cfg.prob:
            continue
        sigma = random.uniform(cfg.sigma_min, cfg.sigma_max)
        kernel = _gaussian_kernel2d(sigma=sigma, device=imgs.device, dtype=imgs.dtype)
        k = kernel.shape[0]
        weight = kernel.view(1, 1, k, k).repeat(c, 1, 1, 1)
        patch = imgs[i : i + 1]
        patch = F.pad(patch, (k // 2, k // 2, k // 2, k // 2), mode="reflect")
        imgs[i : i + 1] = F.conv2d(patch, weight, groups=c)
    return imgs


class PrecisionAgriDetectionTrainer(DetectionTrainer):
    """Custom trainer that injects blur after default Ultralytics preprocessing."""

    blur_cfg = BlurConfig()

    def preprocess_batch(self, batch: dict) -> dict:
        batch = super().preprocess_batch(batch)
        batch["img"] = apply_random_gaussian_blur(batch["img"], self.blur_cfg)
        return batch


def patch_ultralytics(loss_name: LossName = "innermpdiou") -> None:
    global _PATCHED
    if _PATCHED:
        return
    # C2f attention stack replacement.
    tasks.C2f = C2fSimAMEMA
    # Bbox regression loss replacement.
    yolo_loss.BboxLoss.forward = _patched_bboxloss_forward
    yolo_loss.BboxLoss._bbox_loss_mode = loss_name
    _PATCHED = True


def set_loss_mode(loss_name: LossName) -> None:
    yolo_loss.BboxLoss._bbox_loss_mode = loss_name


def unpatch_ultralytics() -> None:
    global _PATCHED
    tasks.C2f = _ORIGINAL_C2F
    yolo_loss.BboxLoss.forward = _ORIGINAL_BBOXLOSS_FORWARD
    yolo_loss.BboxLoss._bbox_loss_mode = "ciou"
    _PATCHED = False
