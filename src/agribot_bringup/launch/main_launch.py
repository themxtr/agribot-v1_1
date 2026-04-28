"""
Agribot v1.1 — Fault-Tolerant Main Launch
==========================================
Performs a hardware inventory *before* any node launches, then
conditionally includes subsystems via IfCondition gates.

Guaranteed boot order:
  1. URDF / TF tree (always)
  2. LiDAR + SLAM   (if /dev/ttyUSB* found)
  3. Camera + CV     (if /dev/video* found AND usb_cam package installed)
  4. Motor control   (if motor serial port found)
  5. System Guard    (always)
  6. RViz2           (always)
"""

import os
import sys

from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    IncludeLaunchDescription,
    LogInfo,
    OpaqueFunction,
)
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PythonExpression
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory
import xacro

# ── Hardware detection (runs at launch-time, before any node) ──────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'agribot_bringup'))
try:
    from agribot_bringup.hw_detection import detect_all, check_ros_package, log_hw_summary
except ImportError:
    # Fallback: module not on sys.path yet (installed mode)
    from agribot_bringup.hw_detection import detect_all, check_ros_package, log_hw_summary


def _print_banner(context, *args, **kwargs):
    hw = detect_all()
    log_hw_summary(hw, logger_fn=lambda m: print(f'[main_launch] {m}'))
    return []


def generate_launch_description():
    # ── Detect hardware ───────────────────────────────────────────────────
    hw = detect_all()
    has_camera_str = 'true' if hw['has_camera'] else 'false'
    has_lidar_str = 'true' if hw['has_lidar'] else 'false'
    has_motor_str = 'true' if hw['has_motor'] else 'false'

    # Check if optional ROS packages are available
    has_usb_cam_pkg = check_ros_package('usb_cam')
    has_slam_pkg = check_ros_package('slam_toolbox')
    has_perception_pkg = check_ros_package('agribot_perception')

    # Camera is only enabled if BOTH hardware and driver package exist
    enable_camera = hw['has_camera'] and has_usb_cam_pkg and has_perception_pkg
    enable_camera_str = 'true' if enable_camera else 'false'

    # SLAM is only enabled if the package is installed
    enable_slam = has_slam_pkg
    enable_slam_str = 'true' if enable_slam else 'false'

    # ── Shared paths ──────────────────────────────────────────────────────
    bringup_dir = get_package_share_directory('agribot_bringup')
    description_dir = get_package_share_directory('agribot_description')

    xacro_file = os.path.join(description_dir, 'urdf', 'agribot.urdf.xacro')
    robot_description_config = xacro.process_file(xacro_file).toxml()
    rviz_config = os.path.join(bringup_dir, 'config', 'agribot_rviz.rviz')

    use_sim_time = LaunchConfiguration('use_sim_time', default='false')

    # ── Launch arguments exposed to the operator ──────────────────────────
    ld = LaunchDescription()

    ld.add_action(DeclareLaunchArgument('use_sim_time', default_value='false'))
    ld.add_action(DeclareLaunchArgument('model_path',
                  default_value='src/agribot_perception/models/yolov8n.onnx'))
    ld.add_action(DeclareLaunchArgument('enable_camera',
                  default_value=enable_camera_str,
                  description='Override: set false to disable camera even if detected'))
    ld.add_action(DeclareLaunchArgument('enable_lidar',
                  default_value=has_lidar_str,
                  description='Override: set false to disable LiDAR even if detected'))
    ld.add_action(DeclareLaunchArgument('enable_motor',
                  default_value=has_motor_str,
                  description='Override: set false to disable motor bridge'))
    ld.add_action(DeclareLaunchArgument('enable_slam',
                  default_value=enable_slam_str,
                  description='Override: set false to disable SLAM'))
    ld.add_action(DeclareLaunchArgument('enable_rviz',
                  default_value='true',
                  description='Set false to run headless (e.g., on Pi without display)'))

    # ── Banner: print detected hardware ───────────────────────────────────
    ld.add_action(OpaqueFunction(function=_print_banner))

    ld.add_action(LogInfo(msg=f'[HW] Camera : {"DETECTED → " + hw["camera_device"] if hw["has_camera"] else "NOT FOUND"}'))
    ld.add_action(LogInfo(msg=f'[HW] LiDAR  : {"DETECTED → " + hw["lidar_device"] if hw["has_lidar"] else "NOT FOUND"}'))
    ld.add_action(LogInfo(msg=f'[HW] Motor  : {"DETECTED → " + hw["motor_device"] if hw["has_motor"] else "NOT FOUND"}'))
    ld.add_action(LogInfo(msg=f'[HW] usb_cam pkg : {"AVAILABLE" if has_usb_cam_pkg else "NOT INSTALLED (camera disabled)"}'))
    ld.add_action(LogInfo(msg=f'[HW] slam_toolbox : {"AVAILABLE" if has_slam_pkg else "NOT INSTALLED (SLAM disabled)"}'))

    # ═══════════════════════════════════════════════════════════════════════
    # ALWAYS-ON: TF Infrastructure
    # ═══════════════════════════════════════════════════════════════════════
    ld.add_action(Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        name='robot_state_publisher',
        output='screen',
        parameters=[{'robot_description': robot_description_config,
                     'use_sim_time': use_sim_time}]
    ))

    ld.add_action(Node(
        package='tf2_ros',
        executable='static_transform_publisher',
        name='static_tf_base_to_laser',
        arguments=['--x', '0.1', '--y', '0', '--z', '0.2',
                   '--yaw', '0', '--pitch', '0', '--roll', '0',
                   '--frame-id', 'base_link', '--child-frame-id', 'laser']
    ))

    # ═══════════════════════════════════════════════════════════════════════
    # CONDITIONAL: LiDAR
    # ═══════════════════════════════════════════════════════════════════════
    ld.add_action(LogInfo(
        condition=IfCondition(LaunchConfiguration('enable_lidar')),
        msg=f'[BOOT] Starting LiDAR on {hw["lidar_device"] or "/dev/ttyUSB0"}'
    ))
    ld.add_action(Node(
        condition=IfCondition(LaunchConfiguration('enable_lidar')),
        package='sllidar_ros2',
        executable='sllidar_node',
        name='sllidar_node',
        parameters=[{
            'channel_type': 'serial',
            'serial_port': hw['lidar_device'] or '/dev/ttyUSB0',
            'serial_baudrate': 115200
        }],
        output='screen'
    ))

    # ═══════════════════════════════════════════════════════════════════════
    # CONDITIONAL: SLAM Toolbox (requires LiDAR)
    # ═══════════════════════════════════════════════════════════════════════
    enable_slam_condition = IfCondition(PythonExpression([
        "'", LaunchConfiguration('enable_lidar'), "' == 'true' and '",
        LaunchConfiguration('enable_slam'), "' == 'true'"
    ]))

    if enable_slam:
        slam_config_path = os.path.join(bringup_dir, 'config', 'slam_toolbox_async.yaml')
        ld.add_action(Node(
            condition=enable_slam_condition,
            package='slam_toolbox',
            executable='async_slam_toolbox_node',
            name='slam_toolbox',
            output='screen',
            parameters=[
                slam_config_path,
                {'use_sim_time': use_sim_time}
            ]
        ))
        ld.add_action(Node(
            condition=enable_slam_condition,
            package='tf2_ros',
            executable='static_transform_publisher',
            name='static_tf_odom_to_base',
            arguments=['--x', '0', '--y', '0', '--z', '0',
                       '--yaw', '0', '--pitch', '0', '--roll', '0',
                       '--frame-id', 'odom', '--child-frame-id', 'base_link']
        ))

    # ═══════════════════════════════════════════════════════════════════════
    # CONDITIONAL: Camera + Perception Pipeline
    # ═══════════════════════════════════════════════════════════════════════
    camera_condition = IfCondition(LaunchConfiguration('enable_camera'))

    if enable_camera:
        ld.add_action(LogInfo(
            condition=camera_condition,
            msg=f'[BOOT] Starting camera on {hw["camera_device"]}'
        ))
        # Camera TF
        ld.add_action(Node(
            condition=camera_condition,
            package='tf2_ros',
            executable='static_transform_publisher',
            name='static_tf_base_to_camera',
            arguments=['--x', '0.15', '--y', '0', '--z', '0.3',
                       '--yaw', '0', '--pitch', '0.3', '--roll', '0',
                       '--frame-id', 'base_link', '--child-frame-id', 'camera_link']
        ))
        # USB Camera
        ld.add_action(Node(
            condition=camera_condition,
            package='usb_cam',
            executable='usb_cam_node_exe',
            name='usb_cam',
            parameters=[{
                'video_device': hw['camera_device'] or '/dev/video0',
                'image_width': 640,
                'image_height': 480,
                'pixel_format': 'yuyv'
            }]
        ))
        # Perception (ONNX)
        from launch_ros.actions import LifecycleNode
        ld.add_action(LifecycleNode(
            condition=camera_condition,
            package='agribot_perception',
            executable='perception_node',
            name='perception_node',
            namespace='',
            output='screen',
            parameters=[{
                'model_path': LaunchConfiguration('model_path'),
                'conf_threshold': 0.85,
                'input_width': 640,
                'input_height': 640,
                'max_fps': 5.0
            }]
        ))
    else:
        ld.add_action(LogInfo(msg='[BOOT] Camera/CV pipeline DISABLED (no camera or driver missing)'))

    # ═══════════════════════════════════════════════════════════════════════
    # CONDITIONAL: Motor Control
    # ═══════════════════════════════════════════════════════════════════════
    motor_condition = IfCondition(LaunchConfiguration('enable_motor'))

    ld.add_action(Node(
        condition=motor_condition,
        package='agribot_control',
        executable='motor_bridge',
        name='motor_bridge',
        parameters=[{
            'port': hw['motor_device'] or '/dev/ttyUSB1',
            'baud': 9600
        }],
        output='screen'
    ))
    ld.add_action(Node(
        condition=motor_condition,
        package='agribot_control',
        executable='spray_controller',
        name='spray_controller',
        parameters=[{'spray_threshold_y': 400, 'target_label': 'weed'}],
        output='screen'
    ))

    # ═══════════════════════════════════════════════════════════════════════
    # ALWAYS-ON: System Guard + RViz2
    # ═══════════════════════════════════════════════════════════════════════
    ld.add_action(Node(
        package='agribot_bringup',
        executable='system_guard',
        name='system_guard',
        output='screen',
        parameters=[{
            'hw_has_camera': enable_camera,
            'hw_has_lidar': hw['has_lidar'],
            'hw_has_motor': hw['has_motor'],
        }]
    ))

    ld.add_action(Node(
        condition=IfCondition(LaunchConfiguration('enable_rviz')),
        package='rviz2',
        executable='rviz2',
        name='rviz2',
        output='screen',
        arguments=['-d', rviz_config]
    ))

    return ld
