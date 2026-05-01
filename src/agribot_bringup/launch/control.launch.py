"""
Control launch — motor bridge + spray controller.
Motor bridge is conditional on serial device presence.
Spray controller always launches (it just listens for /detections).
"""

import os
import sys

from launch import LaunchDescription
from launch.actions import LogInfo
from launch_ros.actions import Node

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'agribot_bringup'))
try:
    from agribot_bringup.hw_detection import detect_motor_controller
except ImportError:
    from agribot_bringup.hw_detection import detect_motor_controller


def generate_launch_description():
    motor_dev = detect_motor_controller()

    ld = LaunchDescription()

    if motor_dev:
        ld.add_action(LogInfo(msg=f'[control] Motor bridge starting on {motor_dev}'))
        ld.add_action(Node(
            package='agribot_control',
            executable='motor_bridge',
            name='motor_bridge',
            parameters=[{'port': motor_dev, 'baud': 9600}],
            output='screen'
        ))
    else:
        ld.add_action(LogInfo(msg='[control] WARNING: No motor controller found. '
                              'Motor bridge DISABLED. Spray controller still active.'))

    ld.add_action(Node(
        package='agribot_control',
        executable='spray_controller',
        name='spray_controller',
        parameters=[{'spray_threshold_y': 400, 'target_label': 'weed'}],
        output='screen'
    ))

    return ld
