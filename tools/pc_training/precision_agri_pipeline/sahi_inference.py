from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from sahi import AutoDetectionModel
from sahi.predict import get_sliced_prediction

try:
    from .common import find_images, read_yaml
except ImportError:
    from common import find_images, read_yaml  # type: ignore


def _resolve_source(data_yaml: Path, split: str) -> Path:
    data = read_yaml(data_yaml)
    root = Path(data.get("path", data_yaml.parent))
    split_rel = data.get(split, data.get("test", "images/test"))
    source = (root / split_rel).resolve()
    if not source.exists():
        raise FileNotFoundError(f"Could not resolve split source directory: {source}")
    return source


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run SAHI sliced inference for high-res agricultural scenes.")
    parser.add_argument("--model", type=Path, default=Path("best.pt"), help="Path to trained YOLO weights.")
    parser.add_argument("--data", type=Path, default=Path("data.yaml"), help="Path to data.yaml.")
    parser.add_argument("--split", type=str, default="test", help="Split key inside data.yaml.")
    parser.add_argument("--source", type=Path, default=None, help="Optional explicit source directory or image path.")
    parser.add_argument("--device", type=str, default="cuda:0")
    parser.add_argument("--conf", type=float, default=0.25)
    parser.add_argument("--slice", type=int, default=640, help="Slice width/height.")
    parser.add_argument("--overlap", type=float, default=0.2, help="Slice overlap ratio.")
    parser.add_argument("--nms-iou", type=float, default=0.75, help="NMS IoU for post-slice merging.")
    parser.add_argument("--output-dir", type=Path, default=Path("runs/precision_agri/sahi_inference"))
    return parser.parse_args()


def run_sahi(args: argparse.Namespace) -> Path:
    source = args.source.resolve() if args.source else _resolve_source(args.data.resolve(), args.split)
    images = [source] if source.is_file() else find_images(source)
    if not images:
        raise RuntimeError(f"No images found at: {source}")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    model = AutoDetectionModel.from_pretrained(
        model_type="ultralytics",
        model_path=str(args.model.resolve()),
        confidence_threshold=args.conf,
        device=args.device,
    )

    coco_predictions = []
    latencies_ms = []
    for image_id, image_path in enumerate(images):
        t0 = time.perf_counter()
        result = get_sliced_prediction(
            str(image_path),
            detection_model=model,
            slice_height=args.slice,
            slice_width=args.slice,
            overlap_height_ratio=args.overlap,
            overlap_width_ratio=args.overlap,
            postprocess_type="NMS",
            postprocess_match_metric="IOU",
            postprocess_match_threshold=args.nms_iou,
        )
        dt_ms = (time.perf_counter() - t0) * 1000.0
        latencies_ms.append(dt_ms)
        coco_predictions.extend(result.to_coco_predictions(image_id=image_id))

    out_json = args.output_dir / "sahi_predictions_coco.json"
    with out_json.open("w", encoding="utf-8") as f:
        json.dump(coco_predictions, f, indent=2)

    avg_ms = sum(latencies_ms) / max(1, len(latencies_ms))
    print(f"SAHI images processed: {len(images)}")
    print(f"Average end-to-end latency (sliced): {avg_ms:.2f} ms/image")
    print(f"Saved COCO predictions: {out_json}")
    return out_json


def main() -> None:
    args = parse_args()
    run_sahi(args)


if __name__ == "__main__":
    main()

