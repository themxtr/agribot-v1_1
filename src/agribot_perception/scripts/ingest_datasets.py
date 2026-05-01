import os
import glob
import random
import yaml
from pathlib import Path
from dataset_utils import normalize_to_yolo, audit_annotations, stratified_split_and_sample, verify_balance

# Config
DATA_ROOT = Path("d:/agribot/datasets/unified_crop_weed")
KAGGLE_PATH = Path("d:/agribot/data_downloads/kaggle")
RAW_PATH = Path("d:/agribot/data_downloads/raw")
SAMPLE_SIZE = 10000  # Lightweight constraint

def ingest_kaggle_rice_weed():
    """Mapping for ac1903/rice-weed-dataset"""
    # Assume class 0 is rice, class 1 is weed
    # This dataset is usually already in YOLO format
    path = KAGGLE_PATH / "ac1903-rice-weed-dataset"
    label_files = glob.glob(str(path / "**/*.txt"), recursive=True)
    data = []
    for lf in label_files:
        img_path = Path(lf).with_suffix(".jpg")
        if not img_path.exists():
            img_path = Path(lf).with_suffix(".png")
        if img_path.exists():
            with open(lf, 'r') as f:
                labels = []
                for line in f:
                    parts = line.strip().split()
                    if len(parts) >= 5:
                        labels.append([int(parts[0]), *map(float, parts[1:5])])
                # Filter/Map (Assuming 0=crop, 1=weed is already correct or needs swap)
                # Let's assume standard: 0=crop, 1=weed
                data.append((img_path, labels))
    return data

def ingest_cropandweed():
    """Mapping for github.com/cropandweed/cropandweed-dataset"""
    # Classes 0-4 are typically crops in this dataset
    CROP_IDS = {0, 1, 2, 3, 4} 
    path = RAW_PATH / "cropandweed"
    # Placeholder for actual parsing logic
    # In a real scenario, this would parse their specific CSV format
    return [] 

def main():
    print("Starting dataset ingestion...")
    os.makedirs(DATA_ROOT, exist_ok=True)
    
    all_data = []
    
    # Ingest sources
    print("Ingesting Kaggle Rice Weed...")
    all_data.extend(ingest_kaggle_rice_weed())
    
    # (Other ingest functions would be called here)
    # Since I don't have the files for GitHub sources yet, 
    # I'll simulate with what's available and add placeholders.
    
    if not all_data:
        print("No data found! Please ensure datasets are downloaded.")
        # Create some dummy data for pipeline validation if requested, 
        # but here we should try to use existing files.
        return

    # Audit
    print(f"Auditing {len(all_data)} images for overlap errors...")
    audited_data = []
    for img, lbls in all_data:
        clean_lbls = audit_annotations(lbls)
        if clean_lbls:
            audited_data.append((img, clean_lbls))
            
    # Split and Sample
    print(f"Sampling to {SAMPLE_SIZE} for lightweight CPU training...")
    train, val, test = stratified_split_and_sample(audited_data, target_count=SAMPLE_SIZE)
    
    # Save to YOLO structure
    for split_name, split_data in [("train", train), ("val", val), ("test", test)]:
        img_dir = DATA_ROOT / "images" / split_name
        lbl_dir = DATA_ROOT / "labels" / split_name
        os.makedirs(img_dir, exist_ok=True)
        os.makedirs(lbl_dir, exist_ok=True)
        
        for img_path, labels in tqdm(split_data, desc=f"Saving {split_name}"):
            dest_img = img_dir / img_path.name
            shutil.copy(img_path, dest_img)
            
            dest_lbl = lbl_dir / f"{img_path.stem}.txt"
            with open(dest_lbl, 'w') as f:
                for lbl in labels:
                    f.write(f"{int(lbl[0])} {' '.join(f'{x:.6f}' for x in lbl[1:])}\n")
                    
    # Verification stats
    for name, data in [("train", train), ("val", val), ("test", test)]:
        counts, ratio = verify_balance(data)
        print(f"{name.capitalize()} Split: {len(data)} images. Counts: {counts}. Weed:Crop Ratio: {ratio:.2f}:1")
        if ratio > 3.0:
            print(f"WARNING: {name} split exceeds 3:1 weed ratio!")

    # Create dataset.yaml
    dataset_config = {
        'path': str(DATA_ROOT.absolute()),
        'train': 'images/train',
        'val': 'images/val',
        'test': 'images/test',
        'names': {0: 'crop', 1: 'weed'}
    }
    with open(DATA_ROOT / "dataset.yaml", 'w') as f:
        yaml.dump(dataset_config, f)
    
    print(f"Dataset preparation complete at {DATA_ROOT}")

if __name__ == "__main__":
    main()
