"""
Perception-only launch for SAHI-wrapped YOLOv8 detection.
Starts usb_cam + lifecycle perception node when camera hardware is present.
"""

import os
import sys

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, LogInfo
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import LifecycleNode, Node

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'agribot_bringup'))
from agribot_bringup.hw_detection import check_ros_package, detect_camera


def generate_launch_description():
    camera_dev = detect_camera()
    has_usb_cam = check_ros_package('usb_cam')
    can_launch = camera_dev is not None and has_usb_cam

    ld = LaunchDescription()
    ld.add_action(
        DeclareLaunchArgument(
            'model_path',
            default_value='runs/agribot_v1_overhaul-4/weights/best.pt',
        )
    )
    ld.add_action(DeclareLaunchArgument('conf_threshold', default_value='0.30'))
    ld.add_action(DeclareLaunchArgument('enable_camera', default_value='true' if can_launch else 'false'))

    if not can_launch:
        reason = 'no camera device' if not camera_dev else 'usb_cam package not installed'
        ld.add_action(LogInfo(msg=f'[perception] skipped: {reason}'))
        return ld

    camera_condition = IfCondition(LaunchConfiguration('enable_camera'))

    ld.add_action(
        Node(
            condition=camera_condition,
            package='usb_cam',
            executable='usb_cam_node_exe',
            name='usb_cam',
            parameters=[
                {
                    'video_device': camera_dev,
                    'image_width': 640,
                    'image_height': 480,
                    'pixel_format': 'yuyv',
                }
            ],
        )
    )

    ld.add_action(
        LifecycleNode(
            condition=camera_condition,
            package='agribot_perception',
            executable='perception_node',
            name='perception_node',
            output='screen',
            parameters=[
                {
                    'model_path': LaunchConfiguration('model_path'),
                    'conf_threshold': LaunchConfiguration('conf_threshold'),
                    'slice_size': 640,
                    'overlap_ratio': 0.2,
                    'nms_iou_threshold': 0.45,
                    'max_fps': 5.0,
                    'show_window': False,
                    'annotated_topic': 'image_annotated',
                }
            ],
        )
    )

    return ld
