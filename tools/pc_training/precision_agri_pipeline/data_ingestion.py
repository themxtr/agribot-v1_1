from __future__ import annotations

import argparse
import random
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
import shutil as shutil_lib

try:
    from .common import (
        CANONICAL_CLASSES,
        CLASS_TO_ID,
        canonicalize_class_name,
        ensure_dir,
        file_hash,
        find_images,
        parse_kaggle_ref,
        read_yaml,
        safe_slug,
        write_yaml,
        yolo_txt_from_labels,
    )
except ImportError:
    from common import (  # type: ignore
        CANONICAL_CLASSES,
        CLASS_TO_ID,
        canonicalize_class_name,
        ensure_dir,
        file_hash,
        find_images,
        parse_kaggle_ref,
        read_yaml,
        safe_slug,
        write_yaml,
        yolo_txt_from_labels,
    )


@dataclass
class Sample:
    image_path: Path
    labels: list[tuple[int, float, float, float, float]]
    source_tag: str
    image_key: str

    @property
    def stratum(self) -> str:
        classes = {label[0] for label in self.labels}
        has_crop = CLASS_TO_ID["crop"] in classes
        has_weed = CLASS_TO_ID["weed"] in classes
        if has_crop and has_weed:
            return "crop+weed"
        if has_weed:
            return "weed-only"
        return "crop-only"


def _run_kaggle_download(dataset_ref: str, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    target_dir = out_dir / safe_slug(dataset_ref)
    if target_dir.exists() and any(target_dir.rglob("*")):
        return target_dir
    kaggle_exe = shutil_lib.which("kaggle")
    if kaggle_exe is not None:
        cmd_prefix = [kaggle_exe]
    else:
        # Fallback for Windows setups where the 'kaggle' console script is not on PATH.
        cmd_prefix = [sys.executable, "-m", "kaggle.cli"]
    target_dir.mkdir(parents=True, exist_ok=True)
    cmd = cmd_prefix + [
        "datasets",
        "download",
        "-d",
        dataset_ref,
        "-p",
        str(target_dir),
        "--unzip",
    ]
    try:
        subprocess.run(cmd, check=True)
    except FileNotFoundError as exc:
        raise RuntimeError(
            "Kaggle CLI was not found. Ensure either `kaggle` is on PATH or "
            "`python -m kaggle.cli --help` works, and configure kaggle.json credentials."
        ) from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"Kaggle download failed for {dataset_ref}. "
            "Verify `%USERPROFILE%\\.kaggle\\kaggle.json` and dataset access."
        ) from exc
    return target_dir


def _find_dataset_yaml(root: Path) -> Path | None:
    candidates = [*root.rglob("*.yaml"), *root.rglob("*.yml")]
    for p in sorted(candidates):
        data = read_yaml(p)
        if "train" in data and "names" in data:
            return p
    return None


def _names_to_map(names_field) -> dict[int, str]:
    if isinstance(names_field, dict):
        return {int(k): str(v) for k, v in names_field.items()}
    if isinstance(names_field, list):
        return {i: str(v) for i, v in enumerate(names_field)}
    return {}


def _label_file_for_image(image_path: Path) -> Path:
    if "images" in image_path.parts:
        parts = list(image_path.parts)
        idx = parts.index("images")
        parts[idx] = "labels"
        return Path(*parts).with_suffix(".txt")
    return image_path.with_suffix(".txt")


def _load_yolo_samples(root: Path, source_tag: str) -> list[Sample]:
    dataset_yaml = _find_dataset_yaml(root)
    class_map: dict[int, str] = {}
    if dataset_yaml:
        class_map = _names_to_map(read_yaml(dataset_yaml).get("names"))

    images = find_images(root)
    samples: list[Sample] = []
    for image_path in images:
        label_path = _label_file_for_image(image_path)
        if not label_path.exists():
            continue
        mapped_labels: list[tuple[int, float, float, float, float]] = []
        lines = label_path.read_text(encoding="utf-8").splitlines()
        for line in lines:
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) != 5:
                continue
            src_idx = int(float(parts[0]))
            cls_name = class_map.get(src_idx, f"class_{src_idx}")
            canonical = canonicalize_class_name(cls_name)
            cls_id = CLASS_TO_ID[canonical]
            x, y, w, h = (float(v) for v in parts[1:])
            if w <= 0.0 or h <= 0.0:
                continue
            mapped_labels.append((cls_id, x, y, w, h))
        if mapped_labels:
            samples.append(
                Sample(
                    image_path=image_path,
                    labels=mapped_labels,
                    source_tag=source_tag,
                    image_key=file_hash(image_path),
                )
            )
    return samples


def _is_detection_dataset(root: Path) -> bool:
    images = find_images(root)
    if not images:
        return False
    probes = images[: min(200, len(images))]
    label_hits = sum(1 for p in probes if _label_file_for_image(p).exists())
    return label_hits / max(1, len(probes)) >= 0.3


def _load_classification_samples(root: Path, source_tag: str, fallback_class: str = "crop") -> list[Sample]:
    split_names = {"train", "val", "valid", "validation", "test", "images", "data"}
    samples: list[Sample] = []
    for image_path in find_images(root):
        # Use nearest non-split folder as class name.
        class_name = None
        for parent in image_path.parents:
            if parent == root:
                break
            p_name = parent.name.strip().lower()
            if p_name and p_name not in split_names:
                class_name = parent.name
                break
        canonical = canonicalize_class_name(class_name or fallback_class, fallback=fallback_class)
        cls_id = CLASS_TO_ID[canonical]
        # Full-image box is valid in normalized YOLO space for classification-only sources.
        labels = [(cls_id, 0.5, 0.5, 1.0, 1.0)]
        samples.append(
            Sample(
                image_path=image_path,
                labels=labels,
                source_tag=source_tag,
                image_key=file_hash(image_path),
            )
        )
    return samples


def _dedupe_samples(samples: list[Sample]) -> list[Sample]:
    seen = set()
    unique: list[Sample] = []
    for sample in samples:
        if sample.image_key in seen:
            continue
        seen.add(sample.image_key)
        unique.append(sample)
    return unique


def _sample_subset(samples: list[Sample], ratio: float, max_samples: int, seed: int) -> list[Sample]:
    if not samples:
        return samples
    ratio = max(0.0, min(1.0, float(ratio)))
    if ratio >= 1.0 and max_samples <= 0:
        return samples
    rng = random.Random(seed)
    pool = samples[:]
    rng.shuffle(pool)
    keep_n = int(len(pool) * ratio) if ratio < 1.0 else len(pool)
    keep_n = max(1, keep_n)
    if max_samples > 0:
        keep_n = min(keep_n, int(max_samples))
    return pool[:keep_n]


def _safe_split(
    items: list[Sample],
    train_ratio: float = 0.8,
    val_ratio: float = 0.1,
    test_ratio: float = 0.1,
    seed: int = 42,
) -> tuple[list[Sample], list[Sample], list[Sample]]:
    if abs((train_ratio + val_ratio + test_ratio) - 1.0) > 1e-9:
        raise ValueError("Split ratios must sum to 1.0")
    if len(items) < 10:
        raise RuntimeError(f"Need at least 10 samples for split, found {len(items)}")

    rng = random.Random(seed)

    bins: dict[str, list[Sample]] = {}
    for item in items:
        bins.setdefault(item.stratum, []).append(item)
    for group in bins.values():
        rng.shuffle(group)

    train_items: list[Sample] = []
    val_items: list[Sample] = []
    test_items: list[Sample] = []

    def split_counts(n: int) -> tuple[int, int, int]:
        train_n = int(n * train_ratio)
        val_n = int(n * val_ratio)
        test_n = n - train_n - val_n
        return train_n, val_n, test_n

    for group in bins.values():
        n = len(group)
        tr_n, va_n, te_n = split_counts(n)
        train_items.extend(group[:tr_n])
        val_items.extend(group[tr_n : tr_n + va_n])
        test_items.extend(group[tr_n + va_n : tr_n + va_n + te_n])

    # Guard against pathological tiny strata resulting in empty splits.
    if not train_items or not val_items or not test_items:
        all_items = items[:]
        rng.shuffle(all_items)
        n = len(all_items)
        tr_n = int(n * train_ratio)
        va_n = int(n * val_ratio)
        train_items = all_items[:tr_n]
        val_items = all_items[tr_n : tr_n + va_n]
        test_items = all_items[tr_n + va_n :]

    rng.shuffle(train_items)
    rng.shuffle(val_items)
    rng.shuffle(test_items)
    return train_items, val_items, test_items


def _export_split(samples: list[Sample], out_root: Path, split: str) -> None:
    image_dir = ensure_dir(out_root / "images" / split)
    label_dir = ensure_dir(out_root / "labels" / split)
    for idx, sample in enumerate(samples):
        stem = f"{safe_slug(sample.source_tag)}_{idx:07d}"
        dst_image = image_dir / f"{stem}{sample.image_path.suffix.lower()}"
        dst_label = label_dir / f"{stem}.txt"
        shutil.copy2(sample.image_path, dst_image)
        dst_label.write_text("\n".join(yolo_txt_from_labels(sample.labels)) + "\n", encoding="utf-8")


def build_unified_dataset(
    dataset_refs: list[str],
    output_dir: Path,
    downloads_dir: Path,
    seed: int = 42,
    allow_partial_downloads: bool = False,
    local_dataset_roots: list[Path] | None = None,
    skip_kaggle_downloads: bool = False,
    online_sample_ratio: float = 1.0,
    online_max_samples: int = 0,
) -> Path:
    random.seed(seed)
    output_dir = output_dir.resolve()
    downloads_dir = downloads_dir.resolve()
    ensure_dir(output_dir)
    ensure_dir(downloads_dir)

    merged_samples: list[Sample] = []

    # Optional local roots bypass Kaggle network requirements.
    for local_root in local_dataset_roots or []:
        root = local_root.resolve()
        if not root.exists():
            print(f"Warning: local dataset root not found, skipping: {root}")
            continue
        source_tag = root.name
        if _is_detection_dataset(root):
            samples = _load_yolo_samples(root, source_tag=source_tag)
        else:
            samples = _load_classification_samples(root, source_tag=source_tag, fallback_class="crop")
        merged_samples.extend(samples)

    skipped_refs: list[str] = []
    if not skip_kaggle_downloads:
        for ref in dataset_refs:
            parsed_ref = parse_kaggle_ref(ref)
            try:
                extracted_root = _run_kaggle_download(parsed_ref, downloads_dir)
            except RuntimeError:
                if allow_partial_downloads:
                    skipped_refs.append(parsed_ref)
                    continue
                raise
            source_tag = parsed_ref.split("/", maxsplit=1)[1]
            if _is_detection_dataset(extracted_root):
                samples = _load_yolo_samples(extracted_root, source_tag=source_tag)
            else:
                samples = _load_classification_samples(extracted_root, source_tag=source_tag, fallback_class="crop")
            samples = _sample_subset(
                samples,
                ratio=online_sample_ratio,
                max_samples=online_max_samples,
                seed=seed,
            )
            merged_samples.extend(samples)

    merged_samples = _dedupe_samples(merged_samples)
    if not merged_samples:
        raise RuntimeError("No valid samples were discovered from the provided datasets.")
    if skipped_refs:
        print(f"Warning: skipped datasets (download unavailable): {', '.join(skipped_refs)}")

    train_items, val_items, test_items = _safe_split(merged_samples, seed=seed)
    _export_split(train_items, output_dir, "train")
    _export_split(val_items, output_dir, "val")
    _export_split(test_items, output_dir, "test")

    yaml_path = output_dir / "data.yaml"
    write_yaml(
        yaml_path,
        {
            "path": str(output_dir),
            "train": "images/train",
            "val": "images/val",
            "test": "images/test",
            "nc": len(CANONICAL_CLASSES),
            "names": {i: name for i, name in enumerate(CANONICAL_CLASSES)},
        },
    )
    return yaml_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download, merge, and normalize Kaggle weed/crop datasets to YOLO.")
    parser.add_argument(
        "--dataset-refs",
        nargs="+",
        default=[
            "https://www.kaggle.com/datasets/ac1903/rice-weed-dataset",
            "https://www.kaggle.com/datasets/nirmalsankalana/rice-leaf-disease-image",
            "https://www.kaggle.com/datasets/jaidalmotra/weed-detection",
        ],
        help="Kaggle dataset URLs or owner/dataset refs.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("datasets/unified_rice_weed_yolo"),
        help="Output YOLO dataset directory.",
    )
    parser.add_argument(
        "--downloads-dir",
        type=Path,
        default=Path("data_downloads/kaggle"),
        help="Directory where Kaggle datasets are downloaded and extracted.",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--allow-partial-downloads",
        action="store_true",
        help="Continue with cached/available datasets when Kaggle CLI or some datasets are unavailable.",
    )
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
    parser.add_argument(
        "--online-sample-ratio",
        type=float,
        default=1.0,
        help="Use only this fraction of each online dataset (0.0-1.0).",
    )
    parser.add_argument(
        "--online-max-samples",
        type=int,
        default=0,
        help="Hard cap per online dataset after sampling (0 disables cap).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    data_yaml = build_unified_dataset(
        dataset_refs=args.dataset_refs,
        output_dir=args.output_dir,
        downloads_dir=args.downloads_dir,
        seed=args.seed,
        allow_partial_downloads=args.allow_partial_downloads,
        local_dataset_roots=args.local_dataset_roots,
        skip_kaggle_downloads=args.skip_kaggle_downloads,
        online_sample_ratio=args.online_sample_ratio,
        online_max_samples=args.online_max_samples,
    )
    print(f"Unified dataset created: {data_yaml}")


if __name__ == "__main__":
    main()
