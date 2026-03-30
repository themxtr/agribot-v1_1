# 🌾 Agribot v1.1 — Autonomous Crop Field Management System

Agribot is a ROS 2 (Humble) based autonomous agricultural rover designed to:
1. **Map** crop fields using SLAM Toolbox and RP-LiDAR
2. **Detect** crops and weeds in real-time using a YOLOv8 camera vision pipeline
3. **Spray** identified weeds automatically via a front-mounted actuator
4. **Navigate** manually or autonomously using keyboard teleop

The system runs on a **Raspberry Pi** (ROS 2 brain) + **Arduino Nano** (real-time motor control) architecture.

---

## 📁 Repository Structure

```
agribot-v1_1/
├── agribot_firmware/          # Arduino Nano firmware (.ino)
├── src/
│   ├── agribot_msgs/          # Custom message definitions
│   ├── agribot_perception/    # YOLOv8 camera detection node
│   ├── agribot_control/       # Spray controller + Arduino serial bridge
│   ├── agribot_bringup/       # All launch files + config
│   │   ├── launch/
│   │   │   ├── main_launch.py       # Full system launch
│   │   │   ├── lidar.launch.py      # LiDAR driver only
│   │   │   ├── navigation.launch.py # SLAM Toolbox mapping
│   │   │   ├── perception.launch.py # Camera + YOLOv8
│   │   │   ├── control.launch.py    # Spray + Motor bridge
│   │   │   └── teleop.launch.py     # Keyboard teleop + Motor bridge
│   │   └── config/
│   │       └── slam_toolbox_async.yaml
│   ├── agribot_description/   # URDF robot model
│   └── agribot_simulation/    # Gazebo simulation world
└── README.md
```

---

## ⚙️ Prerequisites

### System Requirements
- **OS**: Ubuntu 22.04 (or WSL2 on Windows)
- **ROS 2**: Humble Hawksbill
- **Python**: 3.10+

### 1. Install ROS 2 Humble
Follow the official guide: https://docs.ros.org/en/humble/Installation.html

### 2. Install Dependencies
```bash
sudo apt update && sudo apt install -y \
  ros-humble-usb-cam \
  ros-humble-cv-bridge \
  ros-humble-tf2-geometry-msgs \
  ros-humble-gazebo-ros-pkgs \
  ros-humble-slam-toolbox \
  ros-humble-teleop-twist-keyboard \
  ros-humble-robot-state-publisher \
  ros-humble-joint-state-publisher \
  ros-humble-xacro

pip3 install ultralytics opencv-python pyserial
```

### 3. Clone and Build
```bash
# Clone the repository
git clone https://github.com/themxtr/agribot-v1_1.git ~/agribot-v1_1
cd ~/agribot-v1_1

# Clone the RP-LiDAR driver (must be in src/)
git clone https://github.com/Slamtec/sllidar_ros2.git src/sllidar_ros2

# Build
colcon build --symlink-install

# Source the workspace (add this to ~/.bashrc)
source install/setup.bash
```

---

## 🔌 Hardware Connections

### Raspberry Pi → Arduino Nano (Serial)
| Raspberry Pi | Arduino Nano | Purpose |
|:---|:---|:---|
| USB port | USB (native) | Serial command link at 9600 baud |
| `/dev/ttyUSB1` | USB | Motor commands & feedback |

### Arduino Nano → L298N Motor Driver
| Arduino Pin | L298N Pin | Purpose |
|:---|:---|:---|
| D3 (PWM) | ENA | Left motor speed |
| D2 | IN1 | Left motor direction |
| D4 | IN2 | Left motor direction |
| D5 (PWM) | ENB | Right motor speed |
| D7 | IN3 | Right motor direction |
| D8 | IN4 | Right motor direction |

### Arduino Nano → Sensors
| Arduino Pin | Component | Purpose |
|:---|:---|:---|
| D9 | HC-SR04 TRIG | Obstacle detection trigger |
| D10 | HC-SR04 ECHO | Obstacle detection echo |
| A0 | ACS712 OUT | Motor current sensing |

### Raspberry Pi → LiDAR & Camera
| Device | Connection | ROS Topic |
|:---|:---|:---|
| RP-LiDAR (Slamtec) | USB → `/dev/ttyUSB0` | `/scan` |
| USB Camera | USB → `/dev/video0` | `/image_raw` |

---

## 🚀 Launch Files

### 1. Full System (Mapping + Vision + Control)
Starts everything: LiDAR, SLAM, Camera, YOLOv8, Spray, and Motor Bridge.
```bash
ros2 launch agribot_bringup main_launch.py
```

---

### 2. LiDAR Driver Only
Starts the Slamtec RP-LiDAR node and publishes `/scan`.
```bash
ros2 launch agribot_bringup lidar.launch.py
```
> Serial port: `/dev/ttyUSB0` · Baud: `115200`

---

### 3. Mapping (SLAM Toolbox)
Starts SLAM Toolbox in asynchronous mode. Requires LiDAR to be running.
```bash
# Terminal 1
ros2 launch agribot_bringup lidar.launch.py

# Terminal 2
ros2 launch agribot_bringup navigation.launch.py
```
Open **RViz2** and add a **Map** display on topic `/map` to visualize field mapping.

**Save a completed map:**
```bash
ros2 run nav2_map_server map_saver_cli -f ~/agribot_map
```

---

### 4. Perception (Camera + YOLOv8)
Starts the USB camera driver and the YOLOv8 detection node.
```bash
ros2 launch agribot_bringup perception.launch.py
```
- **Subscribes**: `/image_raw`
- **Publishes**: `/detections` (custom `DetectionArray` message)

---

### 5. Control (Spray + Motor Bridge)
Starts the spray controller and the Arduino serial bridge.
```bash
ros2 launch agribot_bringup control.launch.py
```
- **Spray**: subscribes to `/detections`, publishes to `/spray_actuator`
- **Motor Bridge**: subscribes to `/cmd_vel`, sends serial commands to Arduino
- Arduino serial port: `/dev/ttyUSB1`

---

### 6. Manual Keyboard Control (Teleop)
Starts the motor bridge and keyboard teleop together for manual driving.
```bash
ros2 launch agribot_bringup teleop.launch.py
```
**Keyboard controls** (once running):
| Key | Action |
|:---|:---|
| `i` | Forward |
| `,` | Backward |
| `j` | Turn left |
| `l` | Turn right |
| `k` | Stop |
| `q`/`z` | Increase/decrease max speed |

---

### 7. Simulation (Gazebo)
Runs the robot in a virtual Gazebo environment without physical hardware.
```bash
ros2 launch agribot_simulation simulation.launch.py
```

---

## 👁️ Running the Computer Vision (YOLOv8) System

### Step 1 — Install the ML dependency
```bash
pip3 install ultralytics
```

### Step 2 — Get a Weed Detection Model

**Option A: Use the default pretrained YOLOv8 model (no weeds, for testing)**
The system defaults to `yolov8n.pt` which will download automatically on first run.

**Option B: Train a custom weed detection model (recommended)**

1. Go to [Roboflow Universe](https://universe.roboflow.com/) and search for:
   - `"weed detection"` or `"crop and weed"`
   - Recommended: [Crop and Weed Detection](https://universe.roboflow.com/mohamed-traore-2ekkp/crop-and-weed-detection-p6764)

2. Download and train:
```python
from ultralytics import YOLO

model = YOLO('yolov8n.pt')
model.train(
    data='path/to/roboflow/data.yaml',
    epochs=100,
    imgsz=640,
    name='agribot_weed_model'
)
# Output: runs/detect/agribot_weed_model/weights/best.pt
```

### Step 3 — Run the Perception Node
```bash
# With default model
ros2 launch agribot_bringup perception.launch.py

# With your custom trained model
ros2 run agribot_perception detection_node \
  --ros-args -p model_path:=/path/to/best.pt -p confidence_threshold:=0.5
```

### Step 4 — Monitor Detections
```bash
# Watch detection output
ros2 topic echo /detections

# Check camera feed
ros2 run rqt_image_view rqt_image_view
```

### ROS Topics Summary
| Topic | Type | Direction |
|:---|:---|:---|
| `/scan` | `sensor_msgs/LaserScan` | LiDAR → SLAM |
| `/map` | `nav_msgs/OccupancyGrid` | SLAM output |
| `/image_raw` | `sensor_msgs/Image` | Camera → YOLOv8 |
| `/detections` | `agribot_msgs/DetectionArray` | YOLOv8 → Spray controller |
| `/spray_actuator` | `std_msgs/Bool` | Spray command |
| `/cmd_vel` | `geometry_msgs/Twist` | Navigation → Arduino |
| `/motor_feedback` | `std_msgs/String` | Arduino → ROS (`SPEED:x,DIST:x,CURR:x`) |

---

## 🔧 Arduino Firmware

Flash `agribot_firmware/agribot_motor_control.ino` to the Arduino Nano using the Arduino IDE.

**Serial Protocol (9600 baud):**
- `F:200` → Forward at speed 200
- `B:150` → Backward at speed 150
- `L:180` → Turn left at speed 180
- `R:180` → Turn right at speed 180
- `S` → Stop

**Automatic safety**: Motors stop if obstacle detected within 20 cm.

---

## 📎 References

- [Slamtec sllidar_ros2](https://github.com/Slamtec/sllidar_ros2)
- [SLAM Toolbox](https://github.com/SteveMacenski/slam_toolbox)
- [Ultralytics YOLOv8](https://docs.ultralytics.com/)
- [Roboflow Universe](https://universe.roboflow.com/)