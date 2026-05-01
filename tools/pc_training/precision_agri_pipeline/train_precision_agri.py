from __future__ import annotations

import argparse
from pathlib import Path

import torch
from ultralytics import YOLO

try:
    from .model_surgery import PrecisionAgriDetectionTrainer, patch_ultralytics, set_loss_mode
except ImportError:
    from model_surgery import PrecisionAgriDetectionTrainer, patch_ultralytics, set_loss_mode  # type: ignore


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train precision agriculture YOLOv8 with P2 + attention + IoU surgery.")
    parser.add_argument("--data", type=Path, default=Path("data.yaml"), help="Path to YOLO data.yaml")
    parser.add_argument(
        "--model-yaml",
        type=Path,
        default=Path("tools/pc_training/precision_agri_pipeline/models/yolov8_p2_precision.yaml"),
        help="Custom model YAML path.",
    )
    parser.add_argument("--pretrained", type=Path, default=Path("yolov8n.pt"), help="Pretrained .pt for warm start.")
    parser.add_argument("--project", type=Path, default=Path("runs/precision_agri"))
    parser.add_argument("--name", type=str, default="yolov8_p2_simam_ema")
    parser.add_argument("--device", type=str, default="0")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--loss", choices=["piou", "innermpdiou"], default="innermpdiou")
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=2)
    parser.add_argument("--lr0", type=float, default=0.01)
    parser.add_argument("--lrf", type=float, default=0.01)
    parser.add_argument("--weight-decay", type=float, default=0.0005)
    parser.add_argument("--mosaic", type=float, default=1.0)
    parser.add_argument("--close-mosaic", type=int, default=15)
    parser.add_argument("--mixup", type=float, default=0.15)
    parser.add_argument("--hsv-h", type=float, default=0.015)
    parser.add_argument("--hsv-s", type=float, default=0.7)
    parser.add_argument("--hsv-v", type=float, default=0.4)
    parser.add_argument("--warmup-epochs", type=float, default=5.0)
    parser.add_argument("--optimizer", type=str, default="AdamW")
    parser.add_argument(
        "--train-val",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Run validation at each training epoch.",
    )
    parser.add_argument(
        "--cpu-safe",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="When CUDA is unavailable, clamp settings for stable CPU training.",
    )
    return parser.parse_args()


def train(args: argparse.Namespace) -> Path:
    patch_ultralytics(loss_name=args.loss)  # C2f + BBox loss patch
    set_loss_mode(args.loss)

    requested_device = str(args.device).strip().lower()
    effective_device = requested_device
    if requested_device in {"0", "cuda", "cuda:0"} and not torch.cuda.is_available():
        effective_device = "cpu"
        print("CUDA not available. Falling back to device='cpu'.")

    imgsz = int(args.imgsz)
    batch = int(args.batch)
    workers = int(args.workers)
    lr0 = float(args.lr0)
    lrf = float(args.lrf)
    weight_decay = float(args.weight_decay)
    mosaic = float(args.mosaic)
    close_mosaic = int(args.close_mosaic)
    mixup = float(args.mixup)
    hsv_h = float(args.hsv_h)
    hsv_s = float(args.hsv_s)
    hsv_v = float(args.hsv_v)
    warmup_epochs = float(args.warmup_epochs)
    optimizer = str(args.optimizer)
    val_each_epoch = bool(args.train_val)
    conf = None
    max_det = 300
    amp = True
    if effective_device == "cpu" and args.cpu_safe:
        imgsz = min(imgsz, 512)
        batch = min(batch, 1)
        workers = 0
        lr0 = min(lr0, 0.002)
        lrf = max(lrf, 0.05)
        mosaic = min(mosaic, 0.3)
        close_mosaic = 0
        mixup = 0.0
        warmup_epochs = min(warmup_epochs, 2.0)
        val_each_epoch = False
        conf = 0.25
        max_det = 100
        amp = False
        print(
            "CPU-safe profile active -> "
            f"imgsz={imgsz}, batch={batch}, workers={workers}, lr0={lr0}, mosaic={mosaic}, mixup={mixup}, "
            f"val_each_epoch={val_each_epoch}"
        )

    model = YOLO(str(args.model_yaml))
    if args.pretrained.exists():
        model = model.load(str(args.pretrained))

    model.train(
        data=str(args.data),
        imgsz=imgsz,
        epochs=args.epochs,
        batch=batch,
        lr0=lr0,
        lrf=lrf,
        weight_decay=weight_decay,
        mosaic=mosaic,
        close_mosaic=close_mosaic,
        mixup=mixup,
        hsv_h=hsv_h,
        hsv_s=hsv_s,
        hsv_v=hsv_v,
        warmup_epochs=warmup_epochs,
        optimizer=optimizer,
        trainer=PrecisionAgriDetectionTrainer,
        project=str(args.project),
        name=args.name,
        device=effective_device,
        workers=workers,
        seed=args.seed,
        deterministic=True,
        val=val_each_epoch,
        conf=conf,
        max_det=max_det,
        amp=amp,
        plots=False,
        cache=False,
        verbose=True,
    )
    # Resolve to the actual Ultralytics save directory instead of assumed project/name.
    save_dir = None
    if getattr(model, "trainer", None) is not None:
        save_dir = getattr(model.trainer, "save_dir", None)
    if save_dir is not None:
        best = Path(save_dir) / "weights" / "best.pt"
        if best.exists():
            return best
        last = Path(save_dir) / "weights" / "last.pt"
        if last.exists():
            return last
    # Fallback to expected path if trainer metadata is unavailable.
    return args.project / args.name / "weights" / "best.pt"


def main() -> None:
    args = parse_args()
    best_path = train(args)
    print(f"Training finished. Best weights: {best_path}")


if __name__ == "__main__":
    main()
