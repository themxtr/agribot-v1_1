import cv2
import numpy as np
import onnxruntime as ort
import argparse
import time

def validate_onnx(model_path, image_path):
    print(f"--- Validating ONNX model: {model_path} ---")
    
    # 1. Start ONNX Runtime Session
    session = ort.InferenceSession(model_path, providers=['CPUExecutionProvider'])
    input_name = session.get_inputs()[0].name
    input_shape = session.get_inputs()[0].shape # e.g. [1, 3, 640, 640]
    height, width = input_shape[2], input_shape[3]
    
    # 2. Load and Preprocess Image
    img = cv2.imread(image_path)
    if img is None:
        print(f"Error: Could not load image {image_path}")
        return
        
    img_resized = cv2.resize(img, (width, height))
    img_data = img_resized.transpose(2, 0, 1) # HWC to CHW
    img_data = np.expand_dims(img_data, axis=0).astype(np.float32) / 255.0
    
    # 3. Benchmark Inference
    start_time = time.time()
    outputs = session.run(None, {input_name: img_data})
    latency = (time.time() - start_time) * 1000
    print(f"Inference Latency (PC CPU): {latency:.2f} ms")
    
    # 4. Basic Output sanity check
    # YOLOv8 output is usually [1, 84, 8400] (for 80 classes + 4 boxes)
    output = outputs[0]
    print(f"Output Shape: {output.shape}")
    
    if output.ndim == 3 and output.shape[2] > 0:
        print("Success: Model produced detection tensors.")
    else:
        print("Warning: Model output format unexpected.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', type=str, required=True, help='Path to .onnx file')
    parser.add_argument('--image', type=str, required=True, help='Path to test image')
    args = parser.parse_args()
    
    validate_onnx(args.model, args.image)
