import os
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription, DeclareLaunchArgument
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from ament_index_python.packages import get_package_share_directory

def generate_launch_description():
    bringup_dir = get_package_share_directory('agribot_bringup')
    
    # Declare arguments
    use_sim_time = LaunchConfiguration('use_sim_time', default='false')

    # 1. LiDAR
    lidar_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(bringup_dir, 'launch', 'lidar.launch.py'))
    )

    # 2. Hector SLAM
    navigation_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(bringup_dir, 'launch', 'navigation.launch.py'))
    )

    # 3. Perception
    perception_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(bringup_dir, 'launch', 'perception.launch.py')),
        launch_arguments={'model_path': LaunchConfiguration('model_path')}.items()
    )

    # 4. Control
    control_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(bringup_dir, 'launch', 'control.launch.py'))
    )

    ld = LaunchDescription()
    ld.add_action(DeclareLaunchArgument('use_sim_time', default_value='false'))
    ld.add_action(DeclareLaunchArgument('model_path', default_value='src/agribot_perception/models/yolov8n.onnx'))
    ld.add_action(lidar_launch)
    ld.add_action(navigation_launch)
    ld.add_action(perception_launch)
    ld.add_action(control_launch)

    return ld
