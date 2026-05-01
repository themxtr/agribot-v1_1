import os
import cv2
import numpy as np
import shutil
from pathlib import Path
from tqdm import tqdm
import random

def calculate_iou(box1, box2):
    """
    Calculate IoU between two boxes in YOLO format [cls, x, y, w, h].
    Actually, easier if they are [x1, y1, x2, y2].
    """
    # Convert from center-x, center-y, w, h to x1, y1, x2, y2
    def to_xyxy(box):
        _, x, y, w, h = box
        return [x - w/2, y - h/2, x + w/2, y + h/2]

    b1 = to_xyxy(box1)
    b2 = to_xyxy(box2)

    inter_x1 = max(b1[0], b2[0])
    inter_y1 = max(b1[1], b2[1])
    inter_x2 = min(b1[2], b2[2])
    inter_y2 = min(b1[3], b2[3])

    inter_area = max(0, inter_x2 - inter_x1) * max(0, inter_y2 - inter_y1)
    
    area1 = (b1[2] - b1[0]) * (b1[3] - b1[1])
    area2 = (b2[2] - b2[0]) * (b2[3] - b2[1])
    
    union_area = area1 + area2 - inter_area
    if union_area == 0:
        return 0
    return inter_area / union_area

def audit_annotations(labels, iou_threshold=0.6):
    """
    Remove or re-label annotations with high overlap between different classes.
    For this task: if a crop and weed box overlap > threshold, we prioritize crop 
    (or remove as error, per prompt: "remove or re-label"). 
    The prompt says: "remove or re-label any bounding box where a crop and weed label share 
    more than 60% IoU overlap with each other".
    """
    if not labels:
        return []
    
    to_keep = []
    labels = sorted(labels, key=lambda x: x[0]) # Group by class maybe? No, let's check all pairs.
    
    skip_indices = set()
    for i in range(len(labels)):
        if i in skip_indices:
            continue
        for j in range(i + 1, len(labels)):
            if j in skip_indices:
                continue
            
            # If classes are different (0 vs 1)
            if labels[i][0] != labels[j][0]:
                iou = calculate_iou(labels[i], labels[j])
                if iou > iou_threshold:
                    # Overlap error! Remove both or one? 
                    # Prompt says "remove or re-label". 
                    # Let's remove both as they are ambiguous "annotation errors".
                    skip_indices.add(i)
                    skip_indices.add(j)
                    break
        
        if i not in skip_indices:
            to_keep.append(labels[i])
            
    return to_keep

def normalize_to_yolo(source_format, label_data, img_w, img_h, class_mapping):
    """
    Converts various formats to YOLO [cls, x, y, w, h].
    - source_format: 'voc', 'coco', 'csv_cropweed', etc.
    - class_mapping: dict mapping source class to 0 (crop) or 1 (weed).
    """
    yolo_labels = []
    
    if source_format == 'voc':
        # Assume label_data is a list of [cls_name, x1, y1, x2, y2]
        for name, x1, y1, x2, y2 in label_data:
            if name not in class_mapping: continue
            cls = class_mapping[name]
            x_center = (x1 + x2) / (2 * img_w)
            y_center = (y1 + y2) / (2 * img_h)
            w = (x2 - x1) / img_w
            h = (y2 - y1) / img_h
            yolo_labels.append([cls, x_center, y_center, w, h])
            
    elif source_format == 'csv_cropweed':
        # [left, top, right, bottom, label_id]
        for left, top, right, bottom, label_id in label_data:
            if label_id not in class_mapping: continue
            cls = class_mapping[label_id]
            x_center = (left + right) / (2 * img_w)
            y_center = (top + bottom) / (2 * img_h)
            w = (right - left) / img_w
            h = (bottom - top) / img_h
            yolo_labels.append([cls, x_center, y_center, w, h])
            
    elif source_format == 'yolo':
        # Already yolo, just re-map class
        for cls, x, y, w, h in label_data:
            if cls not in class_mapping: continue
            yolo_labels.append([class_mapping[cls], x, y, w, h])
            
    return yolo_labels

def stratified_split_and_sample(data_list, target_count=5000, split_ratios=(0.8, 0.1, 0.1)):
    """
    data_list: list of (img_path, labels)
    target_count: total images to keep (for "lightweight" constraint)
    Returns: train, val, test lists
    """
    random.shuffle(data_list)
    
    # If target_count is provided, sample first
    if target_count and len(data_list) > target_count:
        data_list = data_list[:target_count]
        
    n = len(data_list)
    train_end = int(n * split_ratios[0])
    val_end = train_end + int(n * split_ratios[1])
    
    train = data_list[:train_end]
    val = data_list[train_end:val_end]
    test = data_list[val_end:]
    
    return train, val, test

def verify_balance(data_list):
    """Counts classes in labels and returns ratio."""
    counts = {0: 0, 1: 0}
    for _, labels in data_list:
        for lbl in labels:
            counts[lbl[0]] += 1
    
    weed_to_crop = counts[1] / max(1, counts[0])
    return counts, weed_to_crop
