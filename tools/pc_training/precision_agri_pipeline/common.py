from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Iterable

import yaml

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}
CANONICAL_CLASSES = ["crop", "weed"]
CLASS_TO_ID = {name: idx for idx, name in enumerate(CANONICAL_CLASSES)}


def parse_kaggle_ref(url_or_ref: str) -> str:
    """Extract owner/dataset slug from a Kaggle URL or direct slug."""
    raw = url_or_ref.strip()
    if "kaggle.com/datasets/" in raw:
        raw = raw.split("kaggle.com/datasets/", maxsplit=1)[1]
    raw = raw.strip("/").split("?")[0]
    parts = [p for p in raw.split("/") if p]
    if len(parts) < 2:
        raise ValueError(f"Could not parse Kaggle dataset reference from: {url_or_ref}")
    return f"{parts[0]}/{parts[1]}"


def safe_slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def file_hash(path: Path) -> str:
    h = hashlib.sha1()
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def canonicalize_class_name(name: str, fallback: str = "crop") -> str:
    """Normalize class names across heterogeneous datasets into crop/weed."""
    s = name.strip().lower().replace("_", " ").replace("-", " ")
    weed_keys = ("weed", "grass", "sedge", "broadleaf", "wild")
    crop_keys = ("crop", "plant", "rice", "seedling", "leaf", "paddy")
    if any(k in s for k in weed_keys):
        return "weed"
    if any(k in s for k in crop_keys):
        return "crop"
    return fallback


def find_images(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in IMAGE_EXTS)


def read_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data if isinstance(data, dict) else {}


def write_yaml(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(payload, f, sort_keys=False)


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def yolo_txt_from_labels(labels: Iterable[tuple[int, float, float, float, float]]) -> list[str]:
    return [f"{cls_id} {x:.6f} {y:.6f} {w:.6f} {h:.6f}" for cls_id, x, y, w, h in labels]

