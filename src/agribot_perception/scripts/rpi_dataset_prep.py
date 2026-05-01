#!/usr/bin/env python3
import os
import csv
import cv2
import argparse
from pathlib import Path

class CropAndWeedConverter:
    def __init__(self, use_heuristic_stem=False):
        self.use_heuristic_stem = use_heuristic_stem
        # Mapping from dataset indices to our binary labels
        # Assuming we need to research which IDs are crops and which are weeds from datasets.py
        # For now, let's assume a sample mapping (this should be refined after inspecting datasets.py)
        self.label_map = {
            # Examples: 0-4 might be crops, 5-9 weeds
            # This is a placeholder and MUST be verified
        }

    def convert_bbox_to_yolo(self, img_w, img_h, left, top, right, bottom):
        dw = 1.0 / img_w
        dh = 1.0 / img_h
        x = (left + right) / 2.0
        y = (top + bottom) / 2.0
        w = right - left
        h = bottom - top
        return x*dw, y*dh, w*dw, h*dh

    def get_heuristic_stem(self, left, top, right, bottom):
        # Heuristic: bottom middle of the bounding box
        return (left + right) / 2.0, bottom

    def process_csv(self, csv_path, img_path, output_dir):
        img = cv2.imread(str(img_path))
        if img is None:
            return
        h, w, _ = img.shape
        
        yolo_lines = []
        with open(csv_path, 'r') as f:
            reader = csv.reader(f)
            for row in reader:
                if not row: continue
                # Left, Top, Right, Bottom, Label ID, Stem X, Stem Y
                left, top, right, bottom = map(float, row[:4])
                label_id = int(row[4])
                
                # Determine binary label (0: Crop, 1: Weed)
                # This needs the actual mapping from the repo
                binary_label = 0 if label_id < 5 else 1 # Placeholder logic
                
                y_x, y_y, y_w, y_h = self.convert_bbox_to_yolo(w, h, left, top, right, bottom)
                
                if self.use_heuristic_stem:
                    sx, sy = self.get_heuristic_stem(left, top, right, bottom)
                else:
                    sx, sy = float(row[5]), float(row[6])
                
                # Normalize stem coordinates
                nsx = sx / w
                nsy = sy / h
                
                # YOLO format: <class> <x_center> <y_center> <width> <height> <stem_x> <stem_y>
                yolo_lines.append(f"{binary_label} {y_x:.6f} {y_y:.6f} {y_w:.6f} {y_h:.6f} {nsx:.6f} {nsy:.6f}")
        
        output_txt = Path(output_dir) / f"{img_path.stem}.txt"
        with open(output_txt, 'w') as f:
            f.write("\n".join(yolo_lines))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dataset_root', required=True, help='Path to cropandweed-dataset')
    parser.add_argument('--output_dir', required=True, help='Where to save YOLO labels')
    parser.add_argument('--heuristic', action='store_true', help='Use heuristic stem position')
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    converter = CropAndWeedConverter(use_heuristic_stem=args.heuristic)
    
    # Iterate through images and bboxes
    # ... logic to find pairs ...
    print("Converter script initialized. Ready for dataset processing.")

if __name__ == "__main__":
    main()
