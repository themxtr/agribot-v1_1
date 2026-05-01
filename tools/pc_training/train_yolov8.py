from ultralytics import YOLO
import os
import argparse

def train_and_export(data_yaml, epochs=100, imgsz=640, model_type='yolov8n'):
    """
    Trains a YOLOv8 model on a GPU workstation and exports it to ONNX for Pi 5 deployment.
    """
    print(f"--- Starting Training with {model_type} ---")
    
    # 1. Load the model (Nano version recommended for RPi5)
    model = YOLO(f"{model_type}.pt")
    
    # 2. Train the model
    # Note: Device '0' specifies the first GPU. 
    results = model.train(
        data=data_yaml,
        epochs=epochs,
        imgsz=imgsz,
        plots=True,
        device=0,
        name=f"agribot_{model_type}"
    )
    
    print("--- Training Complete. Evaluating on Validation Set ---")
    metrics = model.val()
    print(f"mAP@50-95: {metrics.box.map}")
    
    # 3. Export to ONNX (Optimized for RPi5 CPU)
    print("--- Exporting to ONNX ---")
    onnx_path = model.export(format='onnx', imgsz=imgsz, simplify=True)
    print(f"Model exported successfully to: {onnx_path}")
    
    return onnx_path

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--data', type=str, default='dataset.yaml', help='Path to data.yaml')
    parser.add_argument('--epochs', type=int, default=100)
    args = parser.parse_args()
    
    # Ensure dataset.yaml exists
    if not os.path.exists(args.data):
        print(f"Error: {args.data} not found. Please provide a valid dataset config.")
    else:
        train_and_export(args.data, epochs=args.epochs)
