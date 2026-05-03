"""
Agribot v1.1 — Simulation Launch File
=====================================
Brings up the complete hardware-free simulation environment in a single command.

Launch arguments:
  scenario    (str,  default="nominal")  — Scenario to run: nominal, camera_loss, error_recovery.
  record_bag  (bool, default=false)      — Record ROS 2 bag of simulation session for replay.

Usage:
  ros2 launch agribot_bringup simulation.launch.py
  ros2 launch agribot_bringup simulation.launch.py scenario:=camera_loss
  ros2 launch agribot_bringup simulation.launch.py record_bag:=true
"""

import os
import datetime

from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    ExecuteProcess,
    IncludeLaunchDescription,
    LogInfo,
)
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory
import xacro


def generate_launch_description():
    """Generate the simulation launch description."""
    # ── Shared paths ────────────────────────────────────────────────────
    bringup_dir = get_package_share_directory('agribot_bringup')
    description_dir = get_package_share_directory('agribot_description')

    xacro_file = os.path.join(description_dir, 'urdf', 'agribot.urdf.xacro')
    robot_description_config = xacro.process_file(xacro_file).toxml()

    # ── Launch Arguments ────────────────────────────────────────────────
    scenario_arg = DeclareLaunchArgument(
        'scenario',
        default_value='nominal',
        description='Simulation scenario: nominal, camera_loss, or error_recovery',
    )
    record_bag_arg = DeclareLaunchArgument(
        'record_bag',
        default_value='false',
        description='Set true to record a rosbag2 of the simulation session',
    )

    scenario = LaunchConfiguration('scenario')
    record_bag = LaunchConfiguration('record_bag')

    # ── Bag output directory ────────────────────────────────────────────
    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    bag_dir = os.path.expanduser(f'~/.ros/agribot_bags/sim_{timestamp}')

    ld = LaunchDescription()
    ld.add_action(scenario_arg)
    ld.add_action(record_bag_arg)

    # ── Banner ──────────────────────────────────────────────────────────
    ld.add_action(LogInfo(msg='=========================================='))
    ld.add_action(LogInfo(msg='🌾 AGRIBOT v1.1 SIMULATION ENVIRONMENT 🌾'))
    ld.add_action(LogInfo(msg='=========================================='))
    ld.add_action(LogInfo(msg='  Dashboard : http://localhost:8080'))
    ld.add_action(LogInfo(msg='  ROS Bridge: ws://localhost:9090'))
    ld.add_action(LogInfo(msg='  Video     : http://localhost:8081/stream?topic=/image_raw/compressed'))
    ld.add_action(LogInfo(msg='  Foxglove  : ws://localhost:8765'))
    ld.add_action(LogInfo(msg='=========================================='))

    # ── 1. Simulation Core (Mock Hardware) ──────────────────────────────
    ld.add_action(Node(
        package='agribot_bringup',
        executable='agribot_sim_core',
        name='agribot_sim_core',
        output='screen',
        parameters=[{'scenario': scenario}],
    ))

    # ── 2. Telemetry Stack ──────────────────────────────────────────────
    ld.add_action(IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(bringup_dir, 'launch', 'telemetry.launch.py')
        ),
        launch_arguments={
            'rosbridge_port': '9090',
            'video_port': '8081',
            'foxglove_port': '8765',
        }.items(),
    ))

    # ── 3. TF Infrastructure ───────────────────────────────────────────
    ld.add_action(Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        name='robot_state_publisher',
        parameters=[{
            'robot_description': robot_description_config,
            'use_sim_time': False,
        }],
    ))

    # Static TF chain: map -> odom -> base_link
    ld.add_action(Node(
        package='tf2_ros',
        executable='static_transform_publisher',
        name='static_tf_map_to_odom',
        arguments=[
            '--x', '0', '--y', '0', '--z', '0',
            '--frame-id', 'map', '--child-frame-id', 'odom',
        ],
    ))
    ld.add_action(Node(
        package='tf2_ros',
        executable='static_transform_publisher',
        name='static_tf_odom_to_base',
        arguments=[
            '--x', '1.0', '--y', '0', '--z', '0',
            '--frame-id', 'odom', '--child-frame-id', 'base_link',
        ],
    ))

    # ── 4. Rosbag2 Recording (optional) ─────────────────────────────────
    # Records logic-relevant topics only; excludes /image_raw/compressed
    # to prevent multi-GB bag files.
    ld.add_action(ExecuteProcess(
        cmd=[
            'ros2', 'bag', 'record',
            '/system_state',
            '/hw_capabilities',
            '/detections',
            '/set_mode',
            '/operator_confirm',
            '/spray_active',
            '/scan',
            '/sim_event',
            '-o', bag_dir,
            '--storage', 'sqlite3',
            '--max-bag-duration', '600',
        ],
        output='screen',
        condition=IfCondition(record_bag),
    ))

    return ld
