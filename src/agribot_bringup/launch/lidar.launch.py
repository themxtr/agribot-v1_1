import os
from launch import LaunchDescription
from launch_ros.actions import Node

def generate_launch_description():
    return LaunchDescription([
        Node(
            package='sllidar_ros2',
            executable='sllidar_node',
            name='sllidar_node',
            parameters=[{'channel_type': 'serial', 'serial_port': '/dev/ttyUSB0', 'serial_baudrate': 115200}],
            output='screen'
        )
    ])
