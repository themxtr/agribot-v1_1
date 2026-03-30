import os
from launch import LaunchDescription
from launch_ros.actions import Node

def generate_launch_description():
    return LaunchDescription([
        Node(
            package='usb_cam',
            executable='usb_cam_node_exe',
            name='usb_cam',
            parameters=[{'video_device': '/dev/video0', 'image_width': 640, 'image_height': 480}]
        ),
        Node(
            package='agribot_perception',
            executable='detection_node',
            name='detection_node',
            parameters=[{'model_path': 'yolov8n.pt', 'confidence_threshold': 0.5}],
            output='screen'
        )
    ])
