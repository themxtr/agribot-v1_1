#!/bin/bash
# Agribot v1.1 — Rosbag2 Replay with Live Dashboard
# Usage: ./simulation/play_bag.sh /path/to/bag_directory
#
# Replays a recorded simulation session while running the full telemetry
# stack so the dashboard at http://localhost:8080 shows the replayed data.
# Note: Video feed is not available during replay (images are not recorded).

set -euo pipefail

BAG_DIR="${1:?Usage: $0 <bag_directory>}"

if [ ! -d "$BAG_DIR" ]; then
    echo "❌ Error: Bag directory '$BAG_DIR' does not exist."
    exit 1
fi

echo "=========================================="
echo "🌾 Agribot Bag Replay"
echo "=========================================="
echo "  Bag: $BAG_DIR"
echo "  Dashboard: http://localhost:8080"
echo "  ROS Bridge: ws://localhost:9090"
echo "=========================================="

# Source ROS 2 environment
source /opt/ros/jazzy/setup.bash
source ~/agribot_ws/install/setup.bash 2>/dev/null || true

# Start telemetry stack in background
echo "Starting telemetry stack..."
ros2 launch agribot_bringup telemetry.launch.py &
TELEMETRY_PID=$!

# Give services time to bind
sleep 3

# Replay bag in a loop
echo "Starting bag replay (Ctrl+C to stop)..."
trap "kill $TELEMETRY_PID 2>/dev/null; exit 0" INT TERM

ros2 bag play --loop "$BAG_DIR"

# Cleanup
kill $TELEMETRY_PID 2>/dev/null
