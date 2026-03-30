import os
from launch import LaunchDescription
from launch_ros.actions import Node

def generate_launch_description():
    return LaunchDescription([
        Node(
            package='agribot_control',
            executable='spray_controller',
            name='spray_controller',
            parameters=[{'spray_threshold_y': 400, 'target_label': 'weed'}],
            output='screen'
        )
    ])
