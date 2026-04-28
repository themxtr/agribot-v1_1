#!/usr/bin/env python3

import os
import shutil
import torch
from ultralytics import YOLO
import yaml
import cv2
import numpy as np

def create_mock_cropweed_dataset(base_path='cropweed_dataset', num_images=10):
    """
    Creates a small mock dataset in YOLO format to validate the pipeline quickly.
    In a real scenario, this would download and extract the actual dataset from
    https://github.com/cropandweed/cropandweed-dataset
    """
    print(f"Creating mock dataset at {base_path} for quick validation...")
    for split in ['train', 'val']:
        images_dir = os.path.join(base_path, 'images', split)
        labels_dir = os.path.join(base_path, 'labels', split)
        os.makedirs(images_dir, exist_ok=True)
        os.makedirs(labels_dir, exist_ok=True)

        for i in range(num_images):
            # Create a dummy image (green for crop, red for weed)
            img = np.zeros((640, 640, 3), dtype=np.uint8)
            
            # Draw a 'crop' (class 0)
            cv2.rectangle(img, (100, 100), (200, 400), (0, 255, 0), -1)
            # Draw a 'weed' (class 1)
            cv2.circle(img, (400, 400), 50, (0, 0, 255), -1)
            
            img_path = os.path.join(images_dir, f"img_{i}.jpg")
            cv2.imwrite(img_path, img)
            
            # YOLO format: class x_center y_center width height (normalized)
            label_path = os.path.join(labels_dir, f"img_{i}.txt")
            with open(label_path, 'w') as f:
                # crop bbox (100,100) to (200,400) -> center (150, 250), w=100, h=300
                f.write(f"0 {150/640:.3f} {250/640:.3f} {100/640:.3f} {300/640:.3f}\n")
                # weed bbox center (400, 400), radius 50 -> center (400, 400), w=100, h=100
                f.write(f"1 {400/640:.3f} {400/640:.3f} {100/640:.3f} {100/640:.3f}\n")
                
    # Create dataset.yaml
    yaml_path = os.path.join(base_path, 'dataset.yaml')
    dataset_config = {
        'path': os.path.abspath(base_path),
        'train': 'images/train',
        'val': 'images/val',
        'names': {
            0: 'crop',
            1: 'weed'
        }
    }
    with open(yaml_path, 'w') as f:
        yaml.dump(dataset_config, f, default_flow_style=False)
        
    return yaml_path

def main():
    print("=== Starting YOLOv8 Training Pipeline ===")
    
    # 1. Device Validation (Crucial for fallback)
    has_cuda = torch.cuda.is_available()
    print(f"PyTorch CUDA Available: {has_cuda}")
    
    device = '0' if has_cuda else 'cpu'
    print(f"Selected Compute Device: {device}")
    
    # 2. Dataset Preparation
    dataset_yaml = create_mock_cropweed_dataset(num_images=5)
    print(f"Dataset prepared. Config: {dataset_yaml}")
    
    # 3. Model Training
    print("Loading YOLOv8n base model...")
    model = YOLO('yolov8n.pt')  # load a pretrained model
    
    print(f"Starting training on device: {device}")
    # Train for 1 epoch just to validate the pipeline works
    results = model.train(
        data=dataset_yaml,
        epochs=1,
        imgsz=640,
        device=device,
        project='runs/train',
        name='crop_weed_model'
    )
    
    # 4. Model Export
    print("Training complete. Exporting model to ONNX format...")
    # ONNX export for our perception node
    export_path = model.export(format='onnx', opset=12)
    print(f"Export successful: {export_path}")
    
    # Also save a copy to the models directory if we can find it
    import shutil
    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        package_models_dir = os.path.join(os.path.dirname(current_dir), 'models')
        os.makedirs(package_models_dir, exist_ok=True)
        
        # Copy PT
        pt_source = os.path.join('runs', 'train', 'crop_weed_model', 'weights', 'best.pt')
        pt_dest = os.path.join(package_models_dir, 'cropweed_best.pt')
        shutil.copy(pt_source, pt_dest)
        print(f"Copied .pt weights to {pt_dest}")
        
        # Copy ONNX
        onnx_source = os.path.join('runs', 'train', 'crop_weed_model', 'weights', 'best.onnx')
        if os.path.exists(onnx_source):
            onnx_dest = os.path.join(package_models_dir, 'cropweed_best.onnx')
            shutil.copy(onnx_source, onnx_dest)
            print(f"Copied .onnx weights to {onnx_dest}")
    except Exception as e:
        print(f"Warning: Failed to copy models to package directory: {e}")

if __name__ == '__main__':
    main()
