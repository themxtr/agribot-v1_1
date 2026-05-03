# 🎮 Agribot v1.1 Simulation Environment

This directory provides a complete, hardware-free simulation of the Agribot platform.
Test the full stack — from ROS 2 state machine to the web dashboard — without physical sensors.

---

## 🚀 Quick Start

```bash
# 1. Build the workspace
colcon build --symlink-install
source install/setup.bash

# 2. Launch simulation (nominal scenario)
ros2 launch agribot_bringup simulation.launch.py

# 3. Open dashboard
# http://localhost:8080
```

---

## 🎭 Scenarios

The simulation supports three predefined fault-injection scenarios,
controlled via the `scenario` launch argument:

### `nominal` (default)
All hardware healthy. Boot sequence: SAFE → CONFIGURING → READY.
Operator activates system, then commands DETECT/SPRAY modes.
```bash
ros2 launch agribot_bringup simulation.launch.py scenario:=nominal
```

### `camera_loss`
System boots normally. After **15 seconds**, the camera feed drops
(stops publishing `/image_raw/compressed` and `/detections`) for **30 seconds**,
simulating a field camera failure. A `WARN: camera_loss` event is published
on `/sim_event`. The dashboard should show the hardware panel reflecting
the lost camera. After 30s the camera auto-recovers.
```bash
ros2 launch agribot_bringup simulation.launch.py scenario:=camera_loss
```

### `error_recovery`
System boots normally. After **10 seconds**, the state machine enters `ERROR`
for 5 seconds (simulating a LiDAR heartbeat loss). It then auto-recovers
through SAFE → CONFIGURING → READY, requiring a fresh `/operator_confirm`
before returning to ACTIVE. Tests the dashboard's ERROR state rendering
and recovery workflow.
```bash
ros2 launch agribot_bringup simulation.launch.py scenario:=error_recovery
```

---

## 📼 Rosbag2 Session Recording

Record all logic-relevant topics (state, detections, modes) to a bag file
for offline replay. **Images are intentionally excluded** to prevent multi-GB bags.

### Recording
```bash
ros2 launch agribot_bringup simulation.launch.py record_bag:=true
# Bags saved to: ~/.ros/agribot_bags/sim_YYYYMMDD_HHMMSS/
# Auto-split at 10-minute boundaries
```

### Replay with Live Dashboard
```bash
chmod +x simulation/play_bag.sh
./simulation/play_bag.sh ~/.ros/agribot_bags/sim_20260503_140000
# Dashboard available at http://localhost:8080
# Video panel shows "Not available in replay mode" fallback
```

---

## 🧪 Verification (CI Smoke Test)

Automated test that verifies topic publication, state transitions,
and emergency stop via rosbridge.

```bash
# Install dependency (once)
pip install roslibpy --break-system-packages

# Run against active simulation
python3 simulation/verify_sim.py

# Test a specific scenario
python3 simulation/verify_sim.py --scenario camera_loss
python3 simulation/verify_sim.py --scenario error_recovery
```

---

## 📦 Components

| File | Purpose |
|------|---------|
| `mock_publishers/agribot_sim_core.py` | Mock hardware node with scenario support |
| `verify_sim.py` | CI smoke test for rosbridge and state machine |
| `play_bag.sh` | Replay recorded bags with live dashboard |
| `tests/test_sim_core_headers.py` | Unit test for CompressedImage headers |
| `README.md` | This file |

---

## 🔌 Port Map

| Service | Port | Protocol |
|---------|------|----------|
| Dashboard (Nginx) | 8080 | HTTP |
| Web Video Server | 8081 | HTTP (MJPEG) |
| ROS Bridge | 9090 | WebSocket |
| Foxglove Bridge | 8765 | WebSocket |

---

## ⚠️ Pre-Launch Checklist

1. **Build workspace**: `colcon build --symlink-install && source install/setup.bash`
2. **Check roslibpy**: `python3 -c "import roslibpy; print(roslibpy.__version__)"`
3. **Verify ports free**: `ss -tlnp | grep -E '8080|8081|9090|8765'`
4. **WSL2 note**: Use `$(hostname -I | awk '{print $1}')` instead of `localhost` for cross-boundary access

---

*Note: This simulation uses wall-clock time (`use_sim_time:=false`) for easier dashboard interaction.*
