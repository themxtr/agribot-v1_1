"""
Perception-only launch — starts camera + ONNX detection if hardware is present.
If no camera is found, prints a diagnostic message and exits cleanly.
"""

import os
import sys

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, LogInfo, OpaqueFunction
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node, LifecycleNode

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'agribot_bringup'))
try:
    from agribot_bringup.hw_detection import detect_camera, check_ros_package
except ImportError:
    from agribot_bringup.hw_detection import detect_camera, check_ros_package


def generate_launch_description():
    camera_dev = detect_camera()
    has_usb_cam = check_ros_package('usb_cam')
    can_launch = camera_dev is not None and has_usb_cam

    ld = LaunchDescription()

    ld.add_action(DeclareLaunchArgument(
        'model_path',
        default_value='src/agribot_perception/models/yolov8n.onnx'))
    ld.add_action(DeclareLaunchArgument(
        'conf_threshold', default_value='0.85'))
    ld.add_action(DeclareLaunchArgument(
        'enable_camera', default_value='true' if can_launch else 'false'))

    if not can_launch:
        reason = 'no camera device' if not camera_dev else 'usb_cam package not installed'
        ld.add_action(LogInfo(msg=f'[perception] SKIPPED — {reason}. '
                              f'Install usb_cam and connect a camera to enable.'))
        return ld

    camera_condition = IfCondition(LaunchConfiguration('enable_camera'))

    # USB Camera
    ld.add_action(Node(
        condition=camera_condition,
        package='usb_cam',
        executable='usb_cam_node_exe',
        name='usb_cam',
        parameters=[{
            'video_device': camera_dev,
            'image_width': 640,
            'image_height': 480,
            'pixel_format': 'yuyv'
        }]
    ))

    # Perception Lifecycle Node (ONNX Runtime)
    ld.add_action(LifecycleNode(
        condition=camera_condition,
        package='agribot_perception',
        executable='perception_node',
        name='perception_node',
        namespace='',
        output='screen',
        parameters=[{
            'model_path': LaunchConfiguration('model_path'),
            'conf_threshold': LaunchConfiguration('conf_threshold'),
            'input_width': 640,
            'input_height': 640,
            'max_fps': 5.0
        }]
    ))

    return ld
