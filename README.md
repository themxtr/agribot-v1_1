# 🌾 Agribot v1.1: Production-Grade Autonomous Weed Management

![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)
![ROS2](https://img.shields.io/badge/ROS2-Humble-orange.svg)
![Platform](https://img.shields.io/badge/Platform-Raspberry%20Pi%205-red.svg)

Agribot is a ROS 2 Humble-based autonomous agricultural robot designed for precision weed management. It is explicitly optimized for real-time execution on the **Raspberry Pi 5**, utilizing a modular architecture, lifecycle-managed nodes, and a predictive latency-compensation pipeline.

---

## 📖 Project Overview

Agribot-v1.1 provides an end-to-end autonomous weeding solution. Unlike high-resource systems, this project targets the Raspberry Pi 5 CPU, using lightweight **YOLOv8n ONNX** models and efficient C++/Python nodes to achieve high precision and deterministic actuation.

### Operational Modes
1.  **SCAN**: Traverses the field using LiDAR and row-detection to build a spatial map of crop lanes.
2.  **DETECT**: High-frequency (5 FPS) visual inference to classify plants as `crop` or `weed`.
3.  **SPRAY**: Targeted actuation with predictive pose compensation to hit weed stems at variable speeds.

---

## ✨ Key Features

-   **RPi5-Optimized Inference**: Replaces heavy GPU stacks with **ONNX Runtime** and **YOLOv8n**.
-   **Lifecycle Nodes**: Managed node states (Configure/Activate/Deactivate) for aggressive CPU/Power management.
-   **Latency Compensation**: Predicts the robot's future pose to trigger the spray nozzle exactly at the target arrival time.
-   **RANSAC Row Detection**: Lightweight geometric mapping of crop rows, eliminating the need for full SLAM in structured fields.
-   **Pre-Fire Validation**: Final verification step to minimize accidental crop damage.

---

## 🏗 System Architecture

| Package | Responsibility |
| :--- | :--- |
| `agribot_msgs` | Custom messages, actions, and services (Detection, SprayAction). |
| `agribot_perception` | ONNX Runtime-based plant detection and dataset preprocessing. |
| `agribot_detection_manager` | Mode orchestration (SCAN, DETECT, SPRAY) via Lifecycle states. |
| `agribot_mapping` | Row detection and coordinate frame transformations. |
| `agribot_actuation` | Action server for predictive spraying and latency modeling. |
| `agribot_bringup` | Master launch files and global configuration management. |
| `agribot_description` | URDF robot model and physical parameters. |

---

## 💻 Software Requirements

### Environment
- **OS**: Ubuntu 22.04 LTS (Jammy Jellyfish)
- **ROS 2**: Humble Hawksbill
- **Python**: 3.10+

### Dependencies
```bash
# System Dependencies
sudo apt update && sudo apt install -y \
  ros-humble-usb-cam ros-humble-cv-bridge \
  ros-humble-tf2-geometry-msgs ros-humble-slam-toolbox \
  ros-humble-teleop-twist-keyboard ros-humble-xacro

# Python ML Runtime
pip3 install onnxruntime opencv-python numpy ultralytics
```

---

## 🛠 Installation & Build

1.  **Clone the Workspace**:
    ```bash
    git clone https://github.com/themxtr/agribot-v1_1.git ~/agribot_ws
    cd ~/agribot_ws
    ```
2.  **Install ROS Dependencies**:
    ```bash
    rosdep install -i --from-path src --rosdistro humble -y
    ```
3.  **Build**:
    ```bash
    colcon build --symlink-install
    source install/setup.bash
    ```

---

## 👁️ Computer Vision Deployment (PC-to-Pi Workflow)

**Important**: YOLOv8 is **not** trained on the Raspberry Pi 5. To ensure production-grade performance, follow this specific "Train on PC, Deploy on Pi" pipeline.

### 1. Training (on Development PC / GPU)
Use a separate machine with a GPU to train your model using the [Ultralytics](https://github.com/ultralytics/ultralytics) library.
```python
from ultralytics import YOLO

# Load a nano model for RPi5 compatibility
model = YOLO('yolov8n.pt') 

# Train on your dataset (e.g., CropAndWeedDataset)
model.train(data='custom_weeds.yaml', epochs=100, imgsz=640)
```

### 2. Export to ONNX (on PC)
Export the trained weights (`best.pt`) to the lightweight **ONNX** format.
```python
model.export(format='onnx') # Produces 'best.onnx'
```

### 3. Deploy to Raspberry Pi 5
Transfer `best.onnx` to the Pi 5 (e.g., via `scp`).
1.  **Placement**: Save to `src/agribot_perception/models/agribot_v8.onnx`.
2.  **Runtime**: The `agribot_perception` node uses **ONNX Runtime (CPU)** to execute the model. No GPU or "Ultralytics installation" is required on the Pi during field execution.

### 4. Performance Expectations
| Param | Target Performance (RPi5 CPU) |
| :--- | :--- |
| **Model** | YOLOv8n (Nano) |
| **Resolution** | 640x640 (standard) or 320x320 (high FPS) |
| **Inference Speed** | 3–5 FPS (standard), ~8 FPS (optimized) |
| **Inference Engine** | ONNX Runtime (CPUExecutionProvider) |
| **CPU Load** | ~60-80% (single core peak) |

---

## 🚀 Running the System

### Full System Launch
Starts LiDAR, Camera, SLAM, Perception, and Control Bridge.
```bash
ros2 launch agribot_bringup main_launch.py model_path:=/path/to/model.onnx
```

### Perception Verification
To run only the camera and weed detection node:
```bash
ros2 launch agribot_bringup perception.launch.py model_path:=/path/to/model.onnx
```
- **Verify Topics**: `ros2 topic echo /detections`
- **Visualize**: `ros2 run rqt_image_view rqt_image_view`

### Mode Switching
Switch between operational modes via String messages:
```bash
# Switch to DETECT mode for active weed tracking
ros2 topic pub /set_mode std_msgs/msg/String "data: 'DETECT'" --once
```

---

## 📏 Calibration Guide

1.  **Camera Intrinsics**: Run `ros2 run camera_calibration cameracalibrator` to eliminate lens distortion.
2.  **Extrinsics (Camera-to-Nozzle)**: Measure physical offset from camera center to nozzle tip. Update the static transform in `agribot_bringup/config/positions.yaml`.
3.  **Latency Modeling**: Tune `system_latency_ms` in the `agribot_actuation` node config. If at speed $V$, the spray hits $D$ meters after the weed, add $(D/V) \times 1000$ to your current latency.

---

## 🔌 Hardware Setup

### Pi to Arduino Serial
- **Port**: `/dev/ttyUSB1` (fixed via udev rules for robustness)
- **Baud**: 9600

### Pinout (Arduino Nano)
| Pin | Component | Description |
| :--- | :--- | :--- |
| **D3/D5** | L298N PWM | Motor Speed Control |
| **D2/D4/D7/D8** | L298N Digital | Forward/Reverse logic |
| **D9/D10** | HC-SR04 | Obstacle avoidance (20cm safety stop) |

---

## 🔧 Troubleshooting

-   **Low FPS**: Ensure the Pi 5 is not thermal throttling. Reduce `imgsz` to 320.
-   **No Detections**: Check if the model input resolution matches the node's `input_width`/`input_height` parameters.
-   **Misaligned Spray**: Re-validate `system_latency_ms`. Ensure robot speed is consistent during spray approach.

---

## 📎 References
- [Ultralytics YOLOv8 Documentation](https://docs.ultralytics.com/)
- [ONNX Runtime Python API](https://onnxruntime.ai/docs/api/python/)
- [ROS2 Humble Documentation](https://docs.ros.org/en/humble/)
