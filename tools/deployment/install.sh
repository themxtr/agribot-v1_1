#!/bin/bash
# 🌾 Agribot v1.1: Production Installer
# Refined by Senior Robotics Engineer Recommendation

set -euo pipefail

echo "=========================================="
echo "🌾 Agribot v1.1 Production Installer"
echo "=========================================="

# 1. OS & Architecture Check
echo "[1/6] Verifying environment..."
if [[ ! -f /etc/os-release ]] || ! grep -q "24.04" /etc/os-release; then
    echo "❌ Error: This script requires Ubuntu 24.04 (Noble Numbat)."
    exit 1
fi
echo "✅ Environment verified."

# 2. Install System Dependencies
echo "[2/6] Installing system packages..."
sudo apt update
sudo apt install -y \
    ros-jazzy-rosbridge-suite \
    ros-jazzy-web-video-server \
    ros-jazzy-foxglove-bridge \
    nginx \
    avahi-daemon \
    python3-pip \
    python3-opencv

# 3. Configure mDNS
echo "[3/6] Setting up mDNS (agribot.local)..."
sudo hostnamectl set-hostname agribot || true
sudo systemctl enable avahi-daemon
sudo systemctl start avahi-daemon

# 4. Configure Nginx Dashboard
echo "[4/6] Configuring Nginx Dashboard..."
DASHBOARD_CONF="/etc/nginx/sites-available/agribot"
sudo cp tools/deployment/nginx/agribot.conf "$DASHBOARD_CONF"
sudo ln -sf "$DASHBOARD_CONF" /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default

echo "  Validating Nginx configuration..."
if sudo nginx -t; then
    echo "  ✅ Nginx config valid."
    sudo systemctl restart nginx
else
    echo "  ❌ Nginx config invalid! Check agribot.conf."
    exit 1
fi

# 5. Install Systemd Services
echo "[5/6] Installing ROS services..."
sudo cp tools/deployment/systemd/agribot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable agribot

# 6. Verification
echo "[6/6] Verifying services..."
ERROR=0

check_port() {
    local port=$1
    local name=$2
    if nc -z localhost "$port" 2>/dev/null; then
        echo "✅ $name is active on port $port"
    else
        echo "⚠️  $name is NOT reachable on port $port"
        ERROR=1
    fi
}

echo "Starting Agribot stack for verification..."
sudo systemctl start agribot
sleep 5

check_port 8080 "Dashboard (Nginx)"
check_port 9090 "ROS Bridge"
check_port 8081 "Video Server"
check_port 8765 "Foxglove Bridge"

echo "=========================================="
if [ $ERROR -eq 0 ]; then
    echo "✅ INSTALLATION SUCCESSFUL!"
    echo "Access your dashboard at http://agribot.local:8080"
else
    echo "❌ INSTALLATION COMPLETED WITH WARNINGS."
    echo "Check 'journalctl -u agribot' for details."
fi
echo "=========================================="
