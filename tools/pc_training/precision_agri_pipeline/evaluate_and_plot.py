from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns
from ultralytics import YOLO

try:
    from .common import find_images, read_yaml
except ImportError:
    from common import find_images, read_yaml  # type: ignore


@dataclass
class DetRecord:
    cls_id: int
    conf: float
    is_tp: int


def xywhn_to_xyxy_abs(label: np.ndarray, w: int, h: int) -> np.ndarray:
    x, y, bw, bh = label
    x1 = (x - bw / 2.0) * w
    y1 = (y - bh / 2.0) * h
    x2 = (x + bw / 2.0) * w
    y2 = (y + bh / 2.0) * h
    return np.array([x1, y1, x2, y2], dtype=np.float32)


def iou_xyxy(box: np.ndarray, boxes: np.ndarray) -> np.ndarray:
    if boxes.size == 0:
        return np.zeros((0,), dtype=np.float32)
    x1 = np.maximum(box[0], boxes[:, 0])
    y1 = np.maximum(box[1], boxes[:, 1])
    x2 = np.minimum(box[2], boxes[:, 2])
    y2 = np.minimum(box[3], boxes[:, 3])
    inter = np.maximum(0.0, x2 - x1) * np.maximum(0.0, y2 - y1)
    area_a = max(0.0, box[2] - box[0]) * max(0.0, box[3] - box[1])
    area_b = np.maximum(0.0, boxes[:, 2] - boxes[:, 0]) * np.maximum(0.0, boxes[:, 3] - boxes[:, 1])
    return inter / (area_a + area_b - inter + 1e-9)


def compute_ap(records: list[DetRecord], n_gt: int) -> float:
    if n_gt == 0:
        return 0.0
    if not records:
        return 0.0
    scores = np.array([r.conf for r in records], dtype=np.float32)
    tps = np.array([r.is_tp for r in records], dtype=np.float32)
    order = np.argsort(-scores)
    tps = tps[order]
    fps = 1.0 - tps
    tp_cum = np.cumsum(tps)
    fp_cum = np.cumsum(fps)
    recall = tp_cum / (n_gt + 1e-9)
    precision = tp_cum / (tp_cum + fp_cum + 1e-9)
    mrec = np.concatenate(([0.0], recall, [1.0]))
    mpre = np.concatenate(([1.0], precision, [0.0]))
    for i in range(mpre.size - 1, 0, -1):
        mpre[i - 1] = max(mpre[i - 1], mpre[i])
    idx = np.where(mrec[1:] != mrec[:-1])[0]
    return float(np.sum((mrec[idx + 1] - mrec[idx]) * mpre[idx + 1]))


def bootstrap_map50(per_class_ap: np.ndarray, n: int = 1000, seed: int = 42) -> tuple[np.ndarray, float, float]:
    rng = np.random.default_rng(seed)
    samples = np.empty((n,), dtype=np.float32)
    for i in range(n):
        draw = rng.choice(per_class_ap, size=len(per_class_ap), replace=True)
        samples[i] = float(np.mean(draw))
    low, high = np.percentile(samples, [2.5, 97.5])
    return samples, float(low), float(high)


def _resolve_split_images(data_yaml: Path, split: str) -> tuple[list[Path], Path]:
    data = read_yaml(data_yaml)
    root = Path(data.get("path", data_yaml.parent))
    images_dir = (root / data.get(split, data.get("test", "images/test"))).resolve()
    if not images_dir.exists():
        raise FileNotFoundError(f"Split path does not exist: {images_dir}")
    return find_images(images_dir), root


def _labels_for_image(image_path: Path, split: str, root: Path) -> Path:
    rel = image_path.relative_to(root)
    parts = list(rel.parts)
    idx = parts.index("images")
    parts[idx] = "labels"
    return root / Path(*parts).with_suffix(".txt")


def _load_gt(labels_path: Path, w: int, h: int) -> tuple[np.ndarray, np.ndarray]:
    if not labels_path.exists():
        return np.zeros((0,), dtype=np.int64), np.zeros((0, 4), dtype=np.float32)
    cls_ids = []
    boxes = []
    for line in labels_path.read_text(encoding="utf-8").splitlines():
        parts = line.strip().split()
        if len(parts) != 5:
            continue
        cls = int(float(parts[0]))
        xywhn = np.array([float(v) for v in parts[1:]], dtype=np.float32)
        cls_ids.append(cls)
        boxes.append(xywhn_to_xyxy_abs(xywhn, w, h))
    if not boxes:
        return np.zeros((0,), dtype=np.int64), np.zeros((0, 4), dtype=np.float32)
    return np.array(cls_ids, dtype=np.int64), np.stack(boxes).astype(np.float32)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate model, export metrics, and generate publication-ready plots.")
    parser.add_argument("--model", type=Path, default=Path("best.pt"))
    parser.add_argument("--data", type=Path, default=Path("data.yaml"))
    parser.add_argument("--split", type=str, default="test")
    parser.add_argument("--imgsz", type=int, default=1280)
    parser.add_argument("--batch", type=int, default=8)
    parser.add_argument("--device", type=str, default="0")
    parser.add_argument("--output-dir", type=Path, default=Path("runs/precision_agri/eval"))
    return parser.parse_args()


def evaluate(args: argparse.Namespace) -> None:
    args.output_dir.mkdir(parents=True, exist_ok=True)
    model = YOLO(str(args.model))

    # Run Ultralytics validation for standard benchmark metrics.
    val_metrics = model.val(
        data=str(args.data),
        split=args.split,
        imgsz=args.imgsz,
        batch=args.batch,
        device=args.device,
        plots=False,
        save_json=False,
        verbose=False,
    )

    names_map = val_metrics.names if hasattr(val_metrics, "names") else model.names
    if isinstance(names_map, list):
        names_map = {i: n for i, n in enumerate(names_map)}
    nc = len(names_map)

    images, root = _resolve_split_images(args.data.resolve(), args.split)
    image_sources = [str(p) for p in images]
    results = model.predict(
        source=image_sources,
        imgsz=args.imgsz,
        conf=0.001,
        iou=0.7,
        device=args.device,
        verbose=False,
        stream=True,
    )

    det_records: dict[int, list[DetRecord]] = {c: [] for c in range(nc)}
    gt_counts = np.zeros((nc,), dtype=np.int64)
    per_image_rows = []
    conf_mat = np.zeros((nc + 1, nc + 1), dtype=np.float64)  # last row/col = background
    speed_rows = []

    for idx, result in enumerate(results):
        # When source is a list, Ultralytics may emit synthetic names (e.g., image0.jpg).
        # Keep a deterministic mapping to the original dataset path by index.
        image_path = images[idx].resolve() if idx < len(images) else Path(result.path).resolve()
        h, w = result.orig_shape
        label_path = _labels_for_image(image_path, args.split, root)
        gt_cls, gt_boxes = _load_gt(label_path, w=w, h=h)
        for c in gt_cls:
            gt_counts[c] += 1

        if result.boxes is None or len(result.boxes) == 0:
            pred_cls = np.zeros((0,), dtype=np.int64)
            pred_conf = np.zeros((0,), dtype=np.float32)
            pred_boxes = np.zeros((0, 4), dtype=np.float32)
        else:
            pred_cls = result.boxes.cls.cpu().numpy().astype(np.int64)
            pred_conf = result.boxes.conf.cpu().numpy().astype(np.float32)
            pred_boxes = result.boxes.xyxy.cpu().numpy().astype(np.float32)

        tp_total = 0
        fp_total = 0
        fn_total = 0

        for c in range(nc):
            gt_idx = np.where(gt_cls == c)[0]
            pd_idx = np.where(pred_cls == c)[0]
            gt_c = gt_boxes[gt_idx] if gt_idx.size else np.zeros((0, 4), dtype=np.float32)
            pd_c = pred_boxes[pd_idx] if pd_idx.size else np.zeros((0, 4), dtype=np.float32)
            conf_c = pred_conf[pd_idx] if pd_idx.size else np.zeros((0,), dtype=np.float32)

            order = np.argsort(-conf_c)
            pd_c = pd_c[order]
            conf_c = conf_c[order]

            matched_gt = set()
            matched_pd = set()
            for j, (box, score) in enumerate(zip(pd_c, conf_c)):
                if gt_c.shape[0] == 0:
                    det_records[c].append(DetRecord(c, float(score), 0))
                    fp_total += 1
                    continue
                ious = iou_xyxy(box, gt_c)
                best = int(np.argmax(ious))
                best_iou = float(ious[best]) if ious.size else 0.0
                if best_iou >= 0.5 and best not in matched_gt:
                    matched_gt.add(best)
                    matched_pd.add(j)
                    det_records[c].append(DetRecord(c, float(score), 1))
                    tp_total += 1
                    conf_mat[c, c] += 1
                else:
                    det_records[c].append(DetRecord(c, float(score), 0))
                    fp_total += 1

            # unmatched GT -> FN (mapped to background column)
            for gi in range(gt_c.shape[0]):
                if gi not in matched_gt:
                    fn_total += 1
                    conf_mat[c, nc] += 1
            # unmatched predictions -> FP (background row)
            for pj in range(pd_c.shape[0]):
                if pj not in matched_pd:
                    conf_mat[nc, c] += 1

        precision = tp_total / max(1, tp_total + fp_total)
        recall = tp_total / max(1, tp_total + fn_total)
        per_image_rows.append(
            {
                "image": str(image_path),
                "tp": tp_total,
                "fp": fp_total,
                "fn": fn_total,
                "precision": precision,
                "recall": recall,
            }
        )
        if isinstance(result.speed, dict):
            speed_rows.append(
                {
                    "preprocess_ms": float(result.speed.get("preprocess", 0.0)),
                    "inference_ms": float(result.speed.get("inference", 0.0)),
                    "postprocess_ms": float(result.speed.get("postprocess", 0.0)),
                }
            )

    per_class_ap50 = np.array([compute_ap(det_records[c], int(gt_counts[c])) for c in range(nc)], dtype=np.float32)
    boot_samples, ci_low, ci_high = bootstrap_map50(per_class_ap50, n=1000, seed=42)

    # F1-confidence curve.
    all_records = [r for rows in det_records.values() for r in rows]
    total_gt = int(gt_counts.sum())
    thresholds = np.linspace(0.0, 1.0, 201)
    f1_values = []
    for thr in thresholds:
        tp = sum(1 for r in all_records if r.conf >= thr and r.is_tp == 1)
        fp = sum(1 for r in all_records if r.conf >= thr and r.is_tp == 0)
        fn = total_gt - tp
        p = tp / max(1, tp + fp)
        r = tp / max(1, tp + fn)
        f1 = 2 * p * r / max(1e-9, p + r)
        f1_values.append(f1)
    f1_values = np.array(f1_values, dtype=np.float32)
    trapezoid_fn = getattr(np, "trapezoid", None)
    if trapezoid_fn is None:
        trapezoid_fn = getattr(np, "trapz")
    f1_auc = float(trapezoid_fn(f1_values, thresholds))

    # Aggregate speed metrics.
    if speed_rows:
        preprocess_ms = float(np.mean([r["preprocess_ms"] for r in speed_rows]))
        inference_ms = float(np.mean([r["inference_ms"] for r in speed_rows]))
        postprocess_ms = float(np.mean([r["postprocess_ms"] for r in speed_rows]))
    else:
        preprocess_ms = inference_ms = postprocess_ms = 0.0

    # Parameter count.
    param_count = int(sum(p.numel() for p in model.model.parameters()))

    summary = {
        "precision": float(val_metrics.box.mp),
        "recall": float(val_metrics.box.mr),
        "mAP50": float(val_metrics.box.map50),
        "mAP50_95": float(val_metrics.box.map),
        "param_count": param_count,
        "latency_ms": {
            "preprocess": preprocess_ms,
            "inference": inference_ms,
            "postprocess": postprocess_ms,
        },
        "bootstrap_mAP50": {
            "samples": 1000,
            "mean": float(boot_samples.mean()),
            "ci95_low": ci_low,
            "ci95_high": ci_high,
        },
    }

    # Save raw tables.
    with (args.output_dir / "metrics_summary.json").open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    with (args.output_dir / "per_class_ap50.json").open("w", encoding="utf-8") as f:
        json.dump({str(k): float(v) for k, v in enumerate(per_class_ap50.tolist())}, f, indent=2)
    with (args.output_dir / "per_image_metrics.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["image", "tp", "fp", "fn", "precision", "recall"])
        writer.writeheader()
        writer.writerows(per_image_rows)

    # Plot 1: normalized confusion matrix (plasma, dark theme).
    plt.style.use("dark_background")
    labels = [names_map[i] for i in range(nc)] + ["background"]
    cm_norm = conf_mat / np.maximum(conf_mat.sum(axis=1, keepdims=True), 1e-9)
    fig, ax = plt.subplots(figsize=(10, 8), dpi=300)
    sns.heatmap(
        cm_norm,
        cmap="plasma",
        annot=True,
        fmt=".2f",
        xticklabels=labels,
        yticklabels=labels,
        cbar=True,
        ax=ax,
    )
    ax.set_title("Normalized Confusion Matrix", color="white", pad=10)
    ax.set_xlabel("Predicted")
    ax.set_ylabel("Ground Truth")
    fig.tight_layout()
    fig.savefig(args.output_dir / "confusion_matrix_plasma_dark.png", dpi=300)
    plt.close(fig)

    # Plot 2: F1-confidence with glow and shaded AUC.
    fig, ax = plt.subplots(figsize=(10, 6), dpi=300)
    ax.fill_between(thresholds, f1_values, color="#00f5d4", alpha=0.22, label=f"AUC={f1_auc:.3f}")
    # Glow effect by stacking progressively wider alpha lines.
    for lw, a in [(10, 0.06), (7, 0.12), (4, 0.2)]:
        ax.plot(thresholds, f1_values, color="#39ff14", linewidth=lw, alpha=a)
    ax.plot(thresholds, f1_values, color="#f8ff00", linewidth=2.8, label="F1 vs Confidence")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_xlabel("Confidence Threshold")
    ax.set_ylabel("F1 Score")
    ax.set_title("F1-Confidence Curve", color="white", pad=10)
    ax.grid(alpha=0.2, color="white")
    ax.legend(loc="best")
    fig.tight_layout()
    fig.savefig(args.output_dir / "f1_confidence_glow_curve.png", dpi=300)
    plt.close(fig)

    # Plot 3: violin distribution of bootstrapped mAP@0.5.
    fig, ax = plt.subplots(figsize=(8, 6), dpi=300)
    sns.violinplot(y=boot_samples, color="#00bbf9", inner="quartile", linewidth=1.2, ax=ax)
    ax.axhline(summary["mAP50"], color="#f15bb5", linestyle="--", linewidth=2, label=f"Observed mAP50={summary['mAP50']:.3f}")
    ax.set_ylabel("Bootstrapped mAP@0.5")
    ax.set_title("Bootstrap Stability of mAP@0.5 (n=1000)", color="white", pad=10)
    ax.legend(loc="lower right")
    ax.grid(alpha=0.15)
    fig.tight_layout()
    fig.savefig(args.output_dir / "bootstrap_map50_violin.png", dpi=300)
    plt.close(fig)

    print(json.dumps(summary, indent=2))
    print(f"Saved evaluation artifacts to: {args.output_dir.resolve()}")


def main() -> None:
    args = parse_args()
    evaluate(args)


if __name__ == "__main__":
    main()
