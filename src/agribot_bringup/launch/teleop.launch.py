import os
from launch import LaunchDescription
from launch_ros.actions import Node

def generate_launch_description():
    return LaunchDescription([
        # 1. Motor Bridge (Communication with Arduino)
        Node(
            package='agribot_control',
            executable='motor_bridge',
            name='motor_bridge',
            parameters=[{'port': '/dev/ttyUSB1', 'baud': 9600}],
            output='screen'
        ),
        
        # 2. Teleop Keyboard (Manual Control)
        # Note: Needs to be run in a terminal that accepts stdin
        Node(
            package='teleop_twist_keyboard',
            executable='teleop_twist_keyboard',
            name='teleop_keyboard',
            output='screen',
            prefix='xterm -e', # Optional: Opens in new terminal if xterm is installed
            shell=True
        )
    ])
