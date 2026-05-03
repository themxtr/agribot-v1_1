#!/bin/bash
# Agribot v1.1 Telemetry Stack Installer
# Run this on your Raspberry Pi 5

set -e

echo "🌾 Agribot v1.1: Telemetry Stack Installer"
echo "=========================================="

# 1. Install Dependencies
echo "[1/4] Installing ROS 2 dependencies..."
sudo apt update
sudo apt install -y \
    ros-jazzy-rosbridge-suite \
    ros-jazzy-web-video-server \
    ros-jazzy-foxglove-bridge \
    avahi-daemon \
    python3-pip

# 2. Setup mDNS and Hostname
echo "[2/4] Configuring mDNS (agribot.local)..."
sudo hostnamectl set-hostname agribot
sudo systemctl enable avahi-daemon
sudo systemctl start avahi-daemon

# 3. Setup Dashboard
echo "[3/4] Preparing Dashboard..."
DASHBOARD_DIR="$HOME/agribot_ws/dashboard"
mkdir -p "$DASHBOARD_DIR"
# Assuming files are copied via scp or git
echo "Make sure to copy dashboard/ files to $DASHBOARD_DIR"

# 4. Install Systemd Services
echo "[4/4] Installing systemd services..."
sudo cp tools/deployment/agribot.service /etc/systemd/system/
sudo cp tools/deployment/dashboard.service /etc/systemd/system/

sudo systemctl daemon-reload
sudo systemctl enable agribot
sudo systemctl enable dashboard

echo "=========================================="
echo "✅ Installation Complete!"
echo "Reboot your Pi or run: sudo systemctl start agribot dashboard"
echo "Access dashboard at: http://agribot.local:8000"
echo "=========================================="
