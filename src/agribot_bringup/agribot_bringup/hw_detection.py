"""
Hardware detection utilities for Agribot v1.1.

Scans /dev for connected peripherals and provides results as a dictionary
that launch files and system_guard can consume to conditionally enable
subsystems.  This module has ZERO ROS dependencies so it can be imported
at launch-file evaluation time (before any node starts).
"""

import glob
import os
import subprocess
import shutil


def detect_camera(video_patterns=('/dev/video*',)):
    """Return the first video device found, or None."""
    for pattern in video_patterns:
        devices = sorted(glob.glob(pattern))
        for dev in devices:
            # Skip metadata devices (v4l2 creates /dev/videoN+1 for metadata)
            try:
                # Quick sanity: check the device is a character device
                if os.path.exists(dev) and os.stat(dev).st_mode & 0o020000:
                    return dev
            except OSError:
                continue
    return None


def detect_lidar(serial_patterns=('/dev/ttyUSB*', '/dev/ttyACM*')):
    """Return the first serial device likely to be a LiDAR, or None.

    Heuristic: the *first* /dev/ttyUSB device is assumed to be the LiDAR.
    For deterministic assignment use udev rules (see README).
    """
    for pattern in serial_patterns:
        devices = sorted(glob.glob(pattern))
        if devices:
            return devices[0]
    return None


def detect_motor_controller(expected_port='/dev/ttyUSB1',
                            fallback_patterns=('/dev/ttyUSB*', '/dev/ttyACM*')):
    """Return the serial port for the Arduino motor controller, or None.

    Checks the expected port first; if absent falls back to the *second*
    ttyUSB device (by convention, LiDAR takes the first).
    """
    if os.path.exists(expected_port):
        return expected_port
    # Fallback: if there are ≥2 serial devices, the second is motor
    for pattern in fallback_patterns:
        devices = sorted(glob.glob(pattern))
        if len(devices) >= 2:
            return devices[1]
    return None


def detect_all():
    """Run full hardware scan and return a capabilities dict.

    Returns
    -------
    dict with keys:
        camera_device   : str | None
        lidar_device    : str | None
        motor_device    : str | None
        has_camera      : bool
        has_lidar       : bool
        has_motor       : bool
    """
    camera = detect_camera()
    lidar = detect_lidar()
    motor = detect_motor_controller()

    return {
        'camera_device': camera,
        'lidar_device': lidar,
        'motor_device': motor,
        'has_camera': camera is not None,
        'has_lidar': lidar is not None,
        'has_motor': motor is not None,
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
