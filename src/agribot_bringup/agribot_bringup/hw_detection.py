"""
Hardware detection utilities for Agribot v1.1.

Scans /dev for connected peripherals and provides results as a dictionary
that launch files and system_guard can consume to conditionally enable
subsystems.  This module has ZERO ROS dependencies so it can be imported
at launch-file evaluation time (before any node starts).
"""

import glob
import os
import serial
import time

def detect_camera(video_patterns=('/dev/video*',)):
    """Return the first video device found, or None."""
    for pattern in video_patterns:
        devices = sorted(glob.glob(pattern))
        for dev in devices:
            try:
                if os.path.exists(dev) and os.stat(dev).st_mode & 0o020000:
                    return dev
            except OSError:
                continue
    return None

def probe_serial_port(port, baudrate=115200, timeout=1.0):
    """Open a port and check if it identifies as an Agribot controller."""
    try:
        # Some Arduinos reset on serial open, so we need to wait a bit
        with serial.Serial(port, baudrate, timeout=timeout) as ser:
            # Send a newline to trigger a response if it's already running
            ser.write(b"\n")
            time.sleep(0.5) # Wait for startup/reset
            
            # Read first few lines
            for _ in range(10):
                line = ser.readline().decode('utf-8', errors='ignore').strip()
                if "STATUS:READY" in line or "Agribot" in line:
                    return "motor"
                if "RPLIDAR" in line or "SLLIDAR" in line: # SLLIDAR usually doesn't output plain text
                    return "lidar"
    except Exception:
        pass
    return "unknown"

def detect_hardware_ports():
    """Scan all serial ports and categorize them."""
    results = {'motor': None, 'lidar': None}
    serial_patterns = ('/dev/ttyUSB*', '/dev/ttyACM*')
    
    available_ports = []
    for pattern in serial_patterns:
        available_ports.extend(glob.glob(pattern))
    
    available_ports = sorted(list(set(available_ports)))
    
    for port in available_ports:
        # Heuristic: sllidar-ros2 is usually aggressive, but we can try to find the motor first
        # because the motor controller outputs clear "STATUS:READY"
        port_type = probe_serial_port(port)
        if port_type == "motor":
            results['motor'] = port
        elif port_type == "lidar":
            results['lidar'] = port
            
    # Fallback for Lidar: if we found the motor, and there is one other port, assume it's Lidar
    if results['motor'] and results['lidar'] is None:
        others = [p for p in available_ports if p != results['motor']]
        if others:
            results['lidar'] = others[0]
            
    return results

def detect_all():
    """Run full hardware scan and return a capabilities dict."""
    camera = detect_camera()
    ports = detect_hardware_ports()

    return {
        'camera_device': camera,
        'lidar_device': ports['lidar'],
        'motor_device': ports['motor'],
        'has_camera': camera is not None,
        'has_lidar': ports['lidar'] is not None,
        'has_motor': ports['motor'] is not None,
    }


def check_ros_package(package_name):
    """Return True if a ROS 2 package is findable via ament_index."""
    try:
        from ament_index_python.packages import get_package_share_directory
        get_package_share_directory(package_name)
        return True
    except Exception:
        return False


def log_hw_summary(hw, logger_fn=print):
    """Pretty-print the hardware inventory."""
    logger_fn('┌─────────────────────────────────────────┐')
    logger_fn('│       AGRIBOT HARDWARE INVENTORY        │')
    logger_fn('├──────────────┬──────────┬───────────────┤')
    logger_fn('│  Subsystem   │  Status  │    Device     │')
    logger_fn('├──────────────┼──────────┼───────────────┤')
    for key, label in [('camera', 'Camera'), ('lidar', 'LiDAR'), ('motor', 'Motor Ctrl')]:
        dev = hw.get(f'{key}_device') or '—'
        status = '   ✅  ' if hw.get(f'has_{key}') else '   ❌  '
        logger_fn(f'│ {label:<12} │{status}│ {dev:<13} │')
    logger_fn('└──────────────┴──────────┴───────────────┘')


def _cli_main():
    """CLI entry point: ``ros2 run agribot_bringup hw_scanner``."""
    hw = detect_all()
    log_hw_summary(hw)

    # Also check ROS packages
    for pkg in ['usb_cam', 'slam_toolbox', 'agribot_perception', 'sllidar_ros2']:
        status = '✅' if check_ros_package(pkg) else '❌'
        print(f'  ROS package {pkg:<24} {status}')


if __name__ == '__main__':
    _cli_main()
