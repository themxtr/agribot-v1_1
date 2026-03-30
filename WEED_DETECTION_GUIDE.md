# Weed Detection: Training & Dataset Guide

To make the Agribot detect weeds effectively, you need a YOLOv8 model trained specifically on agricultural datasets. This guide covers how to find data, train your model, and integrate it into the ROS2 system.

## 1. Finding Datasets on Roboflow

Roboflow is the best place to find pre-annotated weed datasets. Search for these keywords on [Roboflow Universe](https://universe.roboflow.com/):

- **"Sugar Beet Weeds"**: A very popular dataset for identifying weeds among sugar beet crops.
- **"PlantDoc"**: A dataset for plant disease and weed identification.
- **"Crop Weed Detection"**: General datasets containing various crop and weed types.

### Recommended Datasets (Links):
- [Crop and Weed Detection Dataset](https://universe.roboflow.com/mohamed-traore-2ekkp/crop-and-weed-detection-p6764)
- [Weed Detection in Soybean](https://universe.roboflow.com/v-z_l/weed-detection-soybean)

> [!TIP]
> When exporting from Roboflow, choose the **YOLOv8** format.

## 2. Training the YOLOv8 Model

You can train the model on your local machine (if you have an NVIDIA GPU) or use Google Colab.

### Training Script (`train_weeds.py`)
Save this script and run it in an environment with `ultralytics` installed.

```python
from ultralytics import YOLO

# 1. Load a pretrained Nano model (fastest for mobile robots)
model = YOLO('yolov8n.pt')

# 2. Train the model
# Replace 'data.yaml' with the path to the YAML file from Roboflow
results = model.train(
    data='path/to/roboflow/data.yaml',
    epochs=100,
    imgsz=640,
    plots=True,
    name='agribot_weed_model'
)

# 3. Export the model to TorchScript or leave as .pt
model.export(format='torchscript')
```

## 3. Integrating the Trained Model

Once training is complete, follow these steps to use it in the Agribot ROS2 system:

1. **Copy the Model**: Locate your trained model file (usually at `runs/detect/agribot_weed_model/weights/best.pt`) and copy it to your workspace.
2. **Update Launch Parameters**: Modify the `main_launch.py` in `agribot_bringup` to point to your new model.

#### [MODIFY] [main_launch.py](file:///d:/agribot/agribot-v1_1/src/agribot_bringup/launch/main_launch.py#L42)
```python
    # 4. Perception Node (Agribot)
    perception_node = Node(
        package='agribot_perception',
        executable='detection_node',
        name='detection_node',
        parameters=[{
            'model_path': '/absolute/path/to/your/best.pt', # UPDATE THIS
            'confidence_threshold': 0.6
        }]
    )
```

3. **Verify Labels**: Ensure the `target_label` in `agribot_control` matches the class name in your dataset (e.g., "weed").

## 4. How it Works (Logic)

1. **Camera Feed**: The `usb_cam` node publishes raw images to `/image_raw`.
2. **Inference**: The `detection_node.py` runs every frame through your YOLOv8 model.
3. **Filtering**: It identifies objects labeled "weed". If their confidence is above the threshold, it calculates their pixel coordinates.
4. **Coordinate Mapping**: The `DetectionArray` message carries these coordinates to the `spray_controller`.
5. **Action**: The controller triggers the spray if the weed is within the strike zone (e.g., `y > 400` pixels, meaning it's right in front of the bot).
