#!/usr/bin/env python3

from __future__ import annotations

import argparse
import random
from pathlib import Path
from typing import Dict, List

import cv2
import yaml
from ultralytics import YOLO


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def load_dataset_yaml(dataset_yaml: Path) -> Dict:
    with dataset_yaml.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Invalid dataset YAML: {dataset_yaml}")
    return data


def resolve_images_dir(dataset_yaml: Path, split: str, data_cfg: Dict) -> Path:
    root = Path(data_cfg.get("path", dataset_yaml.parent)).resolve()
    split_rel = data_cfg.get(split)
    if not split_rel:
        raise ValueError(f"Dataset YAML missing '{split}' entry: {dataset_yaml}")
    images_dir = (root / split_rel).resolve()
    if not images_dir.exists():
        raise FileNotFoundError(f"Images directory not found: {images_dir}")
    return images_dir


def resolve_weed_class_id(model: YOLO) -> int:
    names = model.names
    if isinstance(names, list):
        name_map = {i: n for i, n in enumerate(names)}
    else:
        name_map = dict(names)
    for class_id, class_name in name_map.items():
        if str(class_name).strip().lower() == "weed":
            return int(class_id)
    return 1


def label_path_from_image(image_path: Path, split: str) -> Path:
    parts = list(image_path.parts)
    try:
        idx = parts.index("images")
        if idx + 1 < len(parts) and parts[idx + 1] == split:
            parts[idx] = "labels"
        else:
            return image_path.with_suffix(".txt")
    except ValueError:
        return image_path.with_suffix(".txt")
    return Path(*parts).with_suffix(".txt")


def gt_has_weed(label_path: Path, weed_class_id: int) -> bool:
    if not label_path.exists():
        return False
    with label_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            class_id = int(float(line.split()[0]))
            if class_id == weed_class_id:
                return True
    return False


def pick_random_images(images_dir: Path, n: int, seed: int) -> List[Path]:
    images = sorted(p for p in images_dir.rglob("*") if p.suffix.lower() in IMAGE_EXTS)
    if not images:
        raise RuntimeError(f"No images found in {images_dir}")
    rng = random.Random(seed)
    return rng.sample(images, k=min(n, len(images)))


def class_color(class_name: str) -> tuple[int, int, int]:
    name = class_name.lower()
    if name == "weed":
        return (0, 0, 255)  # red
    if name == "crop" or name == "plant":
        return (0, 200, 0)  # green
    return (255, 200, 0)  # cyan-ish


def save_annotated_image(
    image_path: Path,
    result,
    names_map: Dict[int, str],
    out_path: Path,
) -> None:
    img = cv2.imread(str(image_path))
    if img is None:
        return

    if result.boxes is None or len(result.boxes) == 0:
        cv2.putText(
            img,
            "No detections",
            (20, 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.0,
            (0, 0, 255),
            2,
            cv2.LINE_AA,
        )
    else:
        for box in result.boxes:
            cls_id = int(box.cls.item())
            conf = float(box.conf.item())
            x1, y1, x2, y2 = [int(v) for v in box.xyxy[0].tolist()]
            label = names_map.get(cls_id, str(cls_id))
            color = class_color(label)
            cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)
            cv2.putText(
                img,
                f"{label} {conf:.2f}",
                (x1, max(20, y1 - 8)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                color,
                2,
                cv2.LINE_AA,
            )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out_path), img)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run weed checks on random dataset images.")
    parser.add_argument("--model", required=True, help="Path to model (.pt or .onnx)")
    parser.add_argument("--dataset", required=True, help="Path to dataset YAML")
    parser.add_argument("--split", default="val", help="Dataset split in YAML (train/val/test)")
    parser.add_argument("--num-samples", type=int, default=5, help="Random images to test")
    parser.add_argument("--conf", type=float, default=0.01, help="Confidence threshold")
    parser.add_argument("--iou", type=float, default=0.7, help="IoU threshold for NMS")
    parser.add_argument("--imgsz", type=int, default=640, help="Inference image size")
    parser.add_argument("--device", default="cpu", help="Inference device (cpu/cuda:0)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument(
        "--output-dir",
        default="runs/random_weed_checks",
        help="Directory to store chosen images and optional annotations",
    )
    parser.add_argument(
        "--save-annotated",
        action="store_true",
        help="Save chosen images with predicted crop/weed borders",
    )
    args = parser.parse_args()

    dataset_yaml = Path(args.dataset).resolve()
    model_path = Path(args.model).resolve()

    data_cfg = load_dataset_yaml(dataset_yaml)
    images_dir = resolve_images_dir(dataset_yaml, args.split, data_cfg)
    sample_paths = pick_random_images(images_dir, args.num_samples, args.seed)

    model = YOLO(str(model_path))
    weed_class_id = resolve_weed_class_id(model)
    names = model.names
    names_map = {i: n for i, n in enumerate(names)} if isinstance(names, list) else dict(names)
    output_dir = Path(args.output_dir).resolve()
    selected_dir = output_dir / "selected_images"
    annotated_dir = output_dir / "annotated_predictions"
    selected_dir.mkdir(parents=True, exist_ok=True)

    print(f"Model: {model_path}")
    print(f"Dataset: {dataset_yaml}")
    print(f"Split: {args.split}")
    print(f"Images tested: {len(sample_paths)}")
    print(f"Weed class ID: {weed_class_id}")
    print(f"Output dir: {output_dir}")
    print("-" * 100)

    correct_presence = 0
    total_weed_preds = 0
    total_preds = 0

    for image_path in sample_paths:
        # Keep a copy of the exact sampled images for review.
        target_copy = selected_dir / image_path.name
        target_copy.write_bytes(image_path.read_bytes())

        result = model.predict(
            source=str(image_path),
            conf=args.conf,
            iou=args.iou,
            imgsz=args.imgsz,
            device=args.device,
            verbose=False,
        )[0]

        pred_classes = [int(c) for c in result.boxes.cls.tolist()] if result.boxes is not None else []
        pred_confs = result.boxes.conf.tolist() if result.boxes is not None else []
        weed_confs = [float(conf) for cls, conf in zip(pred_classes, pred_confs) if cls == weed_class_id]
        pred_has = len(weed_confs) > 0

        label_path = label_path_from_image(image_path, args.split)
        gt_has = gt_has_weed(label_path, weed_class_id)
        presence_ok = pred_has == gt_has

        if args.save_annotated:
            save_annotated_image(
                image_path=image_path,
                result=result,
                names_map=names_map,
                out_path=annotated_dir / image_path.name,
            )

        correct_presence += int(presence_ok)
        total_weed_preds += len(weed_confs)
        total_preds += len(pred_classes)

        top_weed_conf = max(weed_confs) if weed_confs else 0.0
        print(
            f"{image_path.name:28} "
            f"gt_weed={str(gt_has):5} pred_weed={str(pred_has):5} "
            f"weed_boxes={len(weed_confs):2} top_weed_conf={top_weed_conf:.4f} "
            f"presence_match={presence_ok}"
        )

    print("-" * 100)
    print(f"Weed presence accuracy (sample): {correct_presence}/{len(sample_paths)} = {correct_presence/len(sample_paths):.2%}")
    print(f"Total detections (all classes): {total_preds}")
    print(f"Total weed detections: {total_weed_preds}")
    if args.save_annotated:
        print(f"Chosen images copied to: {selected_dir}")
        print(f"Annotated images saved to: {annotated_dir}")


if __name__ == "__main__":
    main()
