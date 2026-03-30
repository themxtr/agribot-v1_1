# Agribot: Autonomous Crop Field Management System

Agribot is an integrated ROS2-based solution for autonomous agricultural rovers. It combines **SLAM Toolbox** for field mapping, YOLOv8 for real-time crop/weed detection, and precise motor/spray control.

## 🚀 Key Features

- **SLAM Toolbox Mapping**: Advanced asynchronous mapping using RP-LIDAR (Native ROS 2).
- **Vision-Driven Perception**: High-speed identification of crops and weeds using a YOLOv8-powered detection node.
- **Intelligent Spraying**: Automated weed extermination via a front-mounted spray system.
- **Hardware Integration**: Arduino Nano motor control with safety sensor overrides.
- **Gazebo Simulation**: Full virtual testing environment for field tasks.

---

## 📦 Installation Guide

### 1. Environment Setup
Recommended: **ROS2 Humble** on Ubuntu 22.04 (or WSL2).

### 2. Install Hardware Drivers & Dependencies
```bash
# Core ROS2 dependencies
sudo apt update
sudo apt install ros-humble-usb-cam \
                 ros-humble-cv-bridge \
                 ros-humble-sllidar-ros2 \
                 ros-humble-tf2-geometry-msgs \
                 ros-humble-gazebo-ros-pkgs \
                 ros-humble-slam-toolbox \
                 ros-humble-teleop-twist-keyboard

# Python dependencies
pip install ultralytics opencv-python pyserial
```

### 3. Build the Workspace
> [!IMPORTANT]
> All packages in this workspace use **ament_python** (no CMake). This avoids legacy ROS 1 build errors and is cleaner for Python-based ROS 2 nodes.
```bash
cd ~/agribot-v1_1
colcon build --symlink-install
source install/setup.bash
```

---

## 🏎️ Running the Bot

### 1. Full System Launch
```bash
ros2 launch agribot_bringup main_launch.py
```

### 2. Manual Control (Teleop)
Control the motors directly via keyboard:
```bash
ros2 launch agribot_bringup teleop.launch.py
```

### 3. Mapping with SLAM Toolbox
To start the mapping process specifically:
```bash
ros2 launch agribot_bringup navigation.launch.py
```
*Open Rviz and add the Map display to see the field as it grows.*

---

## 🤖 Gazebo Simulation
Launch simulation and spawn the rover:
```bash
ros2 launch agribot_simulation simulation.launch.py
```

---

## ⚡ Hardware Wiring (Arduino Nano)
| Component | Arduino Pin |
| :--- | :--- |
| L298N ENA (Left PWM) | D3 |
| L298N ENB (Right PWM) | D5 |
| Ultrasonic Trigger | D9 |
| Ultrasonic Echo | D10 |
| ACS712 Sense | A0 |

---

## 📊 Documentation & References

- [Slam Toolbox Config](src/agribot_bringup/config/slam_toolbox_async.yaml)
- [Arduino Motor Firmware](agribot_firmware/agribot_motor_control.ino)
- [Detection Message Specs](src/agribot_msgs/msg/Detection.msg)
- [Spray Logic Parameters](src/agribot_control/agribot_control/spray_controller.py)