import os
from launch import LaunchDescription
from launch_ros.actions import Node

def generate_launch_description():
    return LaunchDescription([
        Node(
            package='hector_mapping',
            executable='hector_mapping',
            name='hector_mapping',
            parameters=[{
                'map_size': 2048,
                'map_resolution': 0.05,
                'scan_topic': 'scan',
                'base_frame': 'base_link',
                'map_frame': 'map',
                'odom_frame': 'base_link'
            }],
            output='screen'
        )
    ])
