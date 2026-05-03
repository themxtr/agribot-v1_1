"""
Agribot v1.1 — Simulation Launch File
=====================================
Brings up the complete hardware-free simulation environment in a single command.

Launch arguments:
  scenario    (str,  default="nominal")  — Scenario to run: nominal, camera_loss, error_recovery.
  record_bag  (bool, default=false)      — Record ROS 2 bag of simulation session for replay.
  use_rviz    (bool, default=false)      — Launch RViz2 for visualization.
  enable_slam (bool, default=false)      — Launch SLAM Toolbox for mapping.

Usage:
  ros2 launch agribot_bringup simulation.launch.py use_rviz:=true enable_slam:=true
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
from launch.substitutions import LaunchConfiguration, PythonExpression
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
    use_rviz_arg = DeclareLaunchArgument(
        'use_rviz',
        default_value='false',
        description='Set true to launch RViz2',
    )

    scenario = LaunchConfiguration('scenario')
    record_bag = LaunchConfiguration('record_bag')
    use_rviz = LaunchConfiguration('use_rviz')

    enable_slam_arg = DeclareLaunchArgument(
        'enable_slam',
        default_value='false',
        description='Set true to enable SLAM Toolbox',
    )
    enable_slam = LaunchConfiguration('enable_slam')

    # ── Bag output directory ────────────────────────────────────────────
    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    base_bag_dir = os.path.expanduser('~/.ros/agribot_bags')
    os.makedirs(base_bag_dir, exist_ok=True)
    bag_dir = os.path.join(base_bag_dir, f'sim_{timestamp}')

    ld = LaunchDescription()
    ld.add_action(scenario_arg)
    ld.add_action(record_bag_arg)
    ld.add_action(use_rviz_arg)
    ld.add_action(enable_slam_arg)

    # ── Banner ──────────────────────────────────────────────────────────
    ld.add_action(LogInfo(msg='=========================================='))
    ld.add_action(LogInfo(msg='🌾 AGRIBOT v1.1 SIMULATION ENVIRONMENT 🌾'))
    ld.add_action(LogInfo(msg='=========================================='))
    ld.add_action(LogInfo(msg='  Dashboard : http://localhost:8080'))
    ld.add_action(LogInfo(msg='  ROS Bridge: ws://localhost:9090'))
    ld.add_action(LogInfo(msg='  Video     : http://localhost:8081/stream?topic=/image_raw&type=mjpeg'))
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

    # Static TF chain: map -> odom
    # (Only used if SLAM is NOT running)
    ld.add_action(Node(
        condition=IfCondition(PythonExpression(["'", enable_slam, "' == 'false'"])),
        package='tf2_ros',
        executable='static_transform_publisher',
        name='static_tf_map_to_odom',
        arguments=[
            '--x', '0', '--y', '0', '--z', '0',
            '--frame-id', 'map', '--child-frame-id', 'odom',
        ],
    ))

    # SLAM Toolbox: Provides map -> odom based on LiDAR scan
    ld.add_action(Node(
        condition=IfCondition(enable_slam),
        package='slam_toolbox',
        executable='async_slam_toolbox_node',
        name='slam_toolbox',
        parameters=[
            os.path.join(bringup_dir, 'config', 'slam_toolbox_async.yaml'),
            {'use_sim_time': False}
        ],
        output='screen',
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

    # ── 5. Visualization (optional) ─────────────────────────────────────
    ld.add_action(Node(
        package='rviz2',
        executable='rviz2',
        name='rviz2',
        arguments=['-d', os.path.join(bringup_dir, 'config', 'agribot_rviz.rviz')],
        condition=IfCondition(use_rviz),
    ))

    return ld
