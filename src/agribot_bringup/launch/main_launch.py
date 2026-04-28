import os
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription, DeclareLaunchArgument
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory
import xacro

def generate_launch_description():
    bringup_dir = get_package_share_directory('agribot_bringup')
    description_dir = get_package_share_directory('agribot_description')
    
    # Declare arguments
    use_sim_time = LaunchConfiguration('use_sim_time', default='false')

    # Process URDF for robot description
    xacro_file = os.path.join(description_dir, 'urdf', 'agribot.urdf.xacro')
    robot_description_config = xacro.process_file(xacro_file).toxml()

    # RViz2 config
    rviz_config = os.path.join(bringup_dir, 'config', 'agribot_rviz.rviz')

    # --- Sub-launches ---

    # 1. LiDAR
    lidar_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(bringup_dir, 'launch', 'lidar.launch.py'))
    )

    # 2. SLAM Toolbox + TF
    navigation_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(bringup_dir, 'launch', 'navigation.launch.py'))
    )

    # 3. Perception (Camera + YOLOv8n ONNX)
    perception_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(bringup_dir, 'launch', 'perception.launch.py')),
        launch_arguments={'model_path': LaunchConfiguration('model_path')}.items()
    )

    # 4. Control (Spray + Motor Bridge)
    control_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(bringup_dir, 'launch', 'control.launch.py'))
    )

    # --- Standalone Nodes ---

    # Robot State Publisher (URDF → TF tree)
    robot_state_publisher = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        name='robot_state_publisher',
        output='screen',
        parameters=[{
            'robot_description': robot_description_config,
            'use_sim_time': use_sim_time
        }]
    )

    # Static TF: base_link → laser
    static_tf_laser = Node(
        package='tf2_ros',
        executable='static_transform_publisher',
        name='static_tf_base_to_laser',
        arguments=['--x', '0.1', '--y', '0', '--z', '0.2',
                   '--yaw', '0', '--pitch', '0', '--roll', '0',
                   '--frame-id', 'base_link', '--child-frame-id', 'laser']
    )

    # Static TF: base_link → camera_link
    static_tf_camera = Node(
        package='tf2_ros',
        executable='static_transform_publisher',
        name='static_tf_base_to_camera',
        arguments=['--x', '0.15', '--y', '0', '--z', '0.3',
                   '--yaw', '0', '--pitch', '0.3', '--roll', '0',
                   '--frame-id', 'base_link', '--child-frame-id', 'camera_link']
    )

    # System Guard (Safety Monitor)
    system_guard = Node(
        package='agribot_bringup',
        executable='system_guard',
        name='system_guard',
        output='screen'
    )

    # RViz2 (Operator Visualization)
    rviz2 = Node(
        package='rviz2',
        executable='rviz2',
        name='rviz2',
        output='screen',
        arguments=['-d', rviz_config]
    )

    ld = LaunchDescription()
    ld.add_action(DeclareLaunchArgument('use_sim_time', default_value='false'))
    ld.add_action(DeclareLaunchArgument('model_path', default_value='src/agribot_perception/models/yolov8n.onnx'))

    # Core TF infrastructure
    ld.add_action(robot_state_publisher)
    ld.add_action(static_tf_laser)
    ld.add_action(static_tf_camera)

    # Sensor & perception stack
    ld.add_action(lidar_launch)
    ld.add_action(navigation_launch)
    ld.add_action(perception_launch)
    ld.add_action(control_launch)

    # Safety & visualization
    ld.add_action(system_guard)
    ld.add_action(rviz2)

    return ld
