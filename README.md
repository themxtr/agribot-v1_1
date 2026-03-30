# Agribot: Autonomous Crop Field Management System

Agribot is an integrated ROS2-based solution for autonomous agricultural rovers. It combines Hector SLAM for field mapping, YOLOv8 for real-time crop/weed detection, and precise spray control for localized weed management.

## 🚀 Key Features

- **Hector SLAM Mapping**: Create detailed 2D maps of your fields using RP-LIDAR without requiring wheel odometry.
- **Vision-Driven Perception**: High-speed identification of crops and weeds using a YOLOv8-powered detection node.
- **Intelligent Spraying**: Automated weed extermination via a front-mounted spray system triggered by vision proximity.
- **Unified Orchestration**: A single launch file to bring up the entire sensor and processing suite.

## 🛠️ System Architecture

- `agribot_perception`: Vision processing (YOLOv8 + Camera).
- `agribot_control`: Decision-making and spray actuation.
- `agribot_msgs`: Custom ROS2 message interfaces.
- `agribot_bringup`: Master launch system.

---

## 📦 Installation Guide

### 1. Environment Setup
Recommended: **ROS2 Humble** on Ubuntu 22.04 (or WSL2).

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install ROS2 Humble (if not already installed)
# Follow: https://docs.ros.org/en/humble/Installation.html
```

### 2. Install Hardware Drivers & Dependencies
```bash
# Core ROS2 dependencies
sudo apt install ros-humble-usb-cam \
                 ros-humble-cv-bridge \
                 ros-humble-sllidar-ros2 \
                 ros-humble-tf2-geometry-msgs

# Python dependencies
pip install ultralytics opencv-python
```

### 3. Clone Required External Packages

The system provides a base implementation, but you can also integrate these advanced external modules:
- **LiDAR**: [Slamtec sllidar_ros2](https://github.com/Slamtec/sllidar_ros2.git)
- **Vision**: [Robot Vision System](https://github.com/karnamsoujanya330-web/robot-vision-system.git), [Weed Detection (YOLO)](https://github.com/ManasiPandit48/Weed-Detection-usign-Yolo.git)
- **Mapping**: [Hector SLAM](https://github.com/tu-darmstadt-ros-pkg/hector_slam.git), [Real-time 2D Mapping](https://github.com/freecode23/real-time-2D-mapping)
- **Calibration**: [Direct Visual LiDAR Calibration](https://github.com/koide3/direct_visual_lidar_calibration.git)

### 4. Build the Workspace
```bash
cd d:/agribot/agribot-v1_1
colcon build --symlink-install
source install/setup.bash
```

---

## 🏎️ Running the Bot

### 1. Calibrate & Map
Run the master launch file to start sensors, mapping, and detection:
```bash
ros2 launch agribot_bringup main_launch.py
```

### 2. Monitor Output
Open **RViz2** to visualize the map and detections:
```bash
rviz2
# Add Map, RobotModel, and Detection markers (via /detections)
```

### 3. Verify Spray Actuator
The nozzle triggers automatically when a weed label is detected in the bottom 25% of the camera frame. You can monitor the trigger topic:
```bash
ros2 topic echo /spray_actuator
```

---

## 🔧 Hardware Detail Instructions

### RP-LIDAR Setup
- Connection: USB (typically `/dev/ttyUSB0`).
- Ensure the user has permissions: `sudo chmod 666 /dev/ttyUSB0`.

### Camera Setup
- Recommended mounting: Front-facing, angled slightly downwards.
- Default device: `/dev/video0`.

### Spray Actuator
- The `spray_controller` publishes a `std_msgs/Bool` to `/spray_actuator`.
- **High (True)**: Open nozzle.
- **Low (False)**: Close nozzle.
- This signal should be read by an Arduino/GPIO node to control the physical relay/valve.

---

## 🌿 Weed Detection: Training & Dataset Guide

To make the Agribot detect weeds effectively, you need a YOLOv8 model trained specifically on agricultural datasets.

### 1. Finding Datasets on Roboflow
Search for these on [Roboflow Universe](https://universe.roboflow.com/):
- **"Sugar Beet Weeds"**: popular for identifying weeds among sugar beet crops.
- [Crop and Weed Detection Dataset](https://universe.roboflow.com/mohamed-traore-2ekkp/crop-and-weed-detection-p6764)
- [Weed Detection in Soybean](https://universe.roboflow.com/v-z_l/weed-detection-soybean)

### 2. Training the YOLOv8 Model
```python
from ultralytics import YOLO
model = YOLO('yolov8n.pt')
results = model.train(
    data='path/to/roboflow/data.yaml',
    epochs=100,
    imgsz=640,
    name='agribot_weed_model'
)
```

### 3. Integrating the Trained Model
1. Copy your `best.pt` to the workspace.
2. Update `main_launch.py` with the path to your `.pt` file.
3. Ensure `target_label` in `agribot_control` matches your dataset class (e.g., "weed").

---

## 📊 Documentation & References

- [Detection Message Specs](src/agribot_msgs/msg/Detection.msg)
- [Spray Logic Parameters](src/agribot_control/agribot_control/spray_controller.py)
- [Hector SLAM Config](src/agribot_bringup/launch/main_launch.py)