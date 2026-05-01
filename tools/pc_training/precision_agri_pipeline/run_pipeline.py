from __future__ import annotations

import argparse
import importlib
from pathlib import Path

import torch

def _load_attr(module_name: str, attr_name: str):
    try:
        mod = importlib.import_module(f".{module_name}", package=__package__)
    except Exception:
        mod = importlib.import_module(f"tools.pc_training.precision_agri_pipeline.{module_name}")
    return getattr(mod, attr_name)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="End-to-end precision agriculture YOLOv8 pipeline.")
    parser.add_argument("--skip-ingest", action="store_true")
    parser.add_argument("--skip-train", action="store_true")
    parser.add_argument("--skip-sahi", action="store_true")
    parser.add_argument("--skip-eval", action="store_true")
    parser.add_argument(
        "--dataset-refs",
        nargs="+",
        default=[
            "https://www.kaggle.com/datasets/ac1903/rice-weed-dataset",
            "https://www.kaggle.com/datasets/nirmalsankalana/rice-leaf-disease-image",
            "https://www.kaggle.com/datasets/jaidalmotra/weed-detection",
        ],
    )
    parser.add_argument("--downloads-dir", type=Path, default=Path("data_downloads/kaggle"))
    parser.add_argument("--dataset-out", type=Path, default=Path("datasets/unified_rice_weed_yolo"))
    parser.add_argument(
        "--local-dataset-roots",
        nargs="*",
        type=Path,
        default=[],
        help="Optional local dataset roots to merge directly (bypasses Kaggle download).",
    )
    parser.add_argument(
        "--skip-kaggle-downloads",
        action="store_true",
        help="Disable all Kaggle download attempts and use only local/cached datasets.",
    )
    parser.add_argument("--online-sample-ratio", type=float, default=1.0, help="Fraction of each online dataset to add.")
    parser.add_argument("--online-max-samples", type=int, default=0, help="Max samples per online dataset (0=no cap).")
    parser.add_argument("--data", type=Path, default=Path("data.yaml"), help="Existing data.yaml when --skip-ingest.")
    parser.add_argument("--best", type=Path, default=Path("best.pt"), help="Existing best.pt when --skip-train.")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--device", type=str, default="0")
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=2)
    parser.add_argument("--workers", type=int, default=0)
    parser.add_argument(
        "--cpu-safe",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Clamp training settings on CPU for stability.",
    )
    parser.add_argument("--loss", choices=["piou", "innermpdiou"], default="innermpdiou")
    parser.add_argument("--project", type=Path, default=Path("runs/precision_agri"))
    parser.add_argument("--name", type=str, default="yolov8_p2_simam_ema")
    parser.add_argument(
        "--allow-partial-downloads",
        action="store_true",
        help="Continue ingest using only already available datasets when Kaggle download is unavailable.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    requested_device = str(args.device).strip().lower()
    effective_device = requested_device
    if requested_device in {"0", "cuda", "cuda:0"} and not torch.cuda.is_available():
        effective_device = "cpu"
        print("[DEVICE] CUDA unavailable. Using CPU.")

    data_yaml = args.data.resolve()
    if not args.skip_ingest:
        build_unified_dataset = _load_attr("data_ingestion", "build_unified_dataset")
        try:
            data_yaml = build_unified_dataset(
                dataset_refs=args.dataset_refs,
                output_dir=args.dataset_out,
                downloads_dir=args.downloads_dir,
                seed=args.seed,
                allow_partial_downloads=args.allow_partial_downloads,
                local_dataset_roots=args.local_dataset_roots,
                skip_kaggle_downloads=args.skip_kaggle_downloads,
                online_sample_ratio=args.online_sample_ratio,
                online_max_samples=args.online_max_samples,
            )
        except RuntimeError as exc:
            raise RuntimeError(
                f"{exc}\n"
                "Setup Kaggle CLI:\n"
                "1) pip install kaggle\n"
                "2) Put kaggle.json at %USERPROFILE%\\.kaggle\\kaggle.json\n"
                "3) Re-run this command.\n"
                "Or run with --allow-partial-downloads and --local-dataset-roots "
                "to use only local/cached datasets."
            ) from exc
        print(f"[INGEST] data.yaml -> {data_yaml}")
    elif not data_yaml.exists():
        raise FileNotFoundError(f"--skip-ingest set but data.yaml not found: {data_yaml}")

    best = args.best.resolve()
    needs_model = (not args.skip_sahi) or (not args.skip_eval)
    if not args.skip_train:
        train = _load_attr("train_precision_agri", "train")
        train_args = argparse.Namespace(
            data=Path(data_yaml),
            model_yaml=Path("tools/pc_training/precision_agri_pipeline/models/yolov8_p2_precision.yaml"),
            pretrained=Path("yolov8n.pt"),
            project=args.project,
            name=args.name,
            device=effective_device,
            workers=args.workers,
            seed=args.seed,
            loss=args.loss,
            epochs=args.epochs,
            imgsz=args.imgsz,
            batch=args.batch,
            cpu_safe=args.cpu_safe,
            lr0=0.01,
            lrf=0.01,
            weight_decay=0.0005,
            mosaic=1.0,
            close_mosaic=15,
            mixup=0.15,
            hsv_h=0.015,
            hsv_s=0.7,
            hsv_v=0.4,
            warmup_epochs=5.0,
            optimizer="AdamW",
            train_val=True,
        )
        best = train(train_args).resolve()
        print(f"[TRAIN] best.pt -> {best}")
    elif needs_model and not best.exists():
        raise FileNotFoundError(f"--skip-train set but best.pt not found: {best}")

    if not args.skip_sahi:
        run_sahi = _load_attr("sahi_inference", "run_sahi")
        sahi_args = argparse.Namespace(
            model=best,
            data=Path(data_yaml),
            split="test",
            source=None,
            device=("cuda:0" if effective_device == "0" else effective_device),
            conf=0.25,
            slice=640,
            overlap=0.2,
            nms_iou=0.75,
            output_dir=args.project / "sahi_inference",
        )
        run_sahi(sahi_args)

    if not args.skip_eval:
        evaluate = _load_attr("evaluate_and_plot", "evaluate")
        eval_args = argparse.Namespace(
            model=best,
            data=Path(data_yaml),
            split="test",
            imgsz=args.imgsz,
            batch=args.batch,
            device=effective_device,
            output_dir=args.project / "eval",
        )
        evaluate(eval_args)


if __name__ == "__main__":
    main()
