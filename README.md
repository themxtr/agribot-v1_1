# Agribot: Autonomous Crop Field Management System

Agribot is an integrated ROS2-based solution for autonomous agricultural rovers. It combines Hector SLAM for field mapping, YOLOv8 for real-time crop/weed detection, and precise spray control for localized weed management.

## 🚀 Key Features

- **Hector SLAM Mapping**: Create detailed 2D maps of your fields using RP-LIDAR without requiring wheel odometry.
- **Vision-Driven Perception**: High-speed identification of crops and weeds using a YOLOv8-powered detection node.
- **Intelligent Spraying**: Automated weed extermination via a front-mounted spray system triggered by vision proximity.
- **Unified Orchestration**: A single launch file to bring up the entire sensor and processing suite.
- **Hardware Agnostic**: Integrated support for RPLidar, USB Cameras, and Arduino-based motor controllers.

## 🛠️ System Architecture

- `agribot_perception`: Vision processing (YOLOv8 + Camera).
- `agribot_control`: Decision-making, spray actuation, and motor bridge.
- `agribot_msgs`: Custom ROS2 message interfaces.
- `agribot_bringup`: Modular and master launch system.
- `agribot_description`: Physical URDF model for simulation and Rviz.
- `agribot_simulation`: Gazebo field environment.

---

## 📦 Installation Guide

### 1. Environment Setup
Recommended: **ROS2 Humble** on Ubuntu 22.04 (or WSL2).

```bash
# Update system
sudo apt update && sudo apt upgrade -y
```

### 2. Install Hardware Drivers & Dependencies
```bash
# Core ROS2 dependencies
sudo apt install ros-humble-usb-cam \
                 ros-humble-cv-bridge \
                 ros-humble-sllidar-ros2 \
                 ros-humble-tf2-geometry-msgs \
                 ros-humble-gazebo-ros-pkgs

# Python dependencies
pip install ultralytics opencv-python pyserial
```

### 3. Build the Workspace
```bash
cd d:/agribot/agribot-v1_1
colcon build --symlink-install
source install/setup.bash
```

---

## 🏎️ Running the Bot

The system is now modular. You can run the entire stack or individual components.

### 1. Full System Launch
This single command starts LiDAR, Hector SLAM, YOLOv8 Perception, and Spray Control:
```bash
ros2 launch agribot_bringup main_launch.py
```

### 2. Modular Control
- **LiDAR Driver**: `ros2 launch agribot_bringup lidar.launch.py`
- **Hector SLAM Mapping**: `ros2 launch agribot_bringup navigation.launch.py`
- **Vision/Perception**: `ros2 launch agribot_bringup perception.launch.py`
- **Control/Actuation**: `ros2 launch agribot_bringup control.launch.py`
- **Manual Keyboard Control**: `ros2 launch agribot_bringup teleop.launch.py`

---

## 🤖 Gazebo Simulation

If you don't have the physical hardware, you can run the system in a virtual environment.

### 1. Launch Simulation
This opens Gazebo and spawns the Agribot rover:
```bash
ros2 launch agribot_simulation simulation.launch.py
```

### 2. Model Visualization
To view the robot's physical model and sensor frames in Rviz:
```bash
ros2 launch agribot_description display.launch.py
```

---

## ⚡ Motor Control & Hardware (Arduino Nano)

The Agribot uses an **Arduino Nano** as a dedicated real-time controller for the L298N motor drivers and safety sensors.

### 1. Wiring Diagram
| Component | Arduino Pin | Description |
| :--- | :--- | :--- |
| **L298N ENA** | D3 (PWM) | Left Motor Speed |
| **L298N IN1/2** | D2, D4 | Left Motor Direction |
| **L298N ENB** | D5 (PWM) | Right Motor Speed |
| **L298N IN3/4** | D7, D8 | Right Motor Direction |
| **HC-SR04 TRIG** | D9 | Ultrasonic Trigger |
| **HC-SR04 ECHO** | D10 | Ultrasonic Echo |
| **ACS712 SENSE** | A0 | Current Measurement |

### 2. Serial Protocol (9600 Baud)
The Raspberry Pi sends high-level commands, and the Arduino Nano handles the PWM and safety overrides.
- `F:speed` - Forward
- `B:speed` - Backward
- `L:speed` - Turn Left
- `R:speed` - Turn Right
- `S` - Stop
- **Speed**: 0-255

### 3. Safety & Feedback
The Arduino automatically stops motors if an obstacle is detected within **20cm**. It reports status every 500ms:
`SPEED:xxx,DIST:xxx,CURR:xxx`

---

## 🌿 Weed Detection: Training & Dataset Guide

To make the Agribot detect weeds effectively, you need a YOLOv8 model trained specifically on agricultural datasets.

### 1. Finding Datasets on Roboflow
Search for these on [Roboflow Universe](https://universe.roboflow.com/):
- **"Sugar Beet Weeds"**: popular for identifying weeds among sugar beet crops.
- [Crop and Weed Detection Dataset](https://universe.roboflow.com/mohamed-traore-2ekkp/crop-and-weed-detection-p6764)

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

---

## 📊 Documentation & References

- [Arduino Firmware](agribot_firmware/agribot_motor_control.ino)
- [ROS2 Motor Bridge](src/agribot_control/agribot_control/motor_bridge.py)
- [Detection Message Specs](src/agribot_msgs/msg/Detection.msg)
- [Spray Logic Parameters](src/agribot_control/agribot_control/spray_controller.py)
- [Simulation Config](src/agribot_simulation/launch/simulation.launch.py)