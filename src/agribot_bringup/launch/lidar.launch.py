"""
LiDAR launch — auto-detects serial device for RPLiDAR.
If no serial device is found, prints a warning and returns empty.
"""

import os
import sys

from launch import LaunchDescription
from launch.actions import LogInfo
from launch_ros.actions import Node

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'agribot_bringup'))
try:
    from agribot_bringup.hw_detection import detect_lidar
except ImportError:
    from agribot_bringup.hw_detection import detect_lidar


def generate_launch_description():
    lidar_dev = detect_lidar()

    ld = LaunchDescription()

    if lidar_dev is None:
        ld.add_action(LogInfo(msg='[lidar] WARNING: No LiDAR serial device found. '
                              'Plug in the RPLiDAR and re-launch.'))
        return ld

    ld.add_action(LogInfo(msg=f'[lidar] Starting sllidar_node on {lidar_dev}'))
    ld.add_action(Node(
        package='sllidar_ros2',
        executable='sllidar_node',
        name='sllidar_node',
        parameters=[{
            'channel_type': 'serial',
            'serial_port': lidar_dev,
            'serial_baudrate': 115200
        }],
        output='screen'
    ))

    return ld
