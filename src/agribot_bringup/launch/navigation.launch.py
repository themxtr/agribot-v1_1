import os
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory

def generate_launch_description():
    bringup_dir = get_package_share_directory('agribot_bringup')
    
    # Slam Toolbox parameters
    slam_config_path = os.path.join(bringup_dir, 'config', 'slam_toolbox_async.yaml')

    return LaunchDescription([
        # 1. SLAM Toolbox Node
        Node(
            package='slam_toolbox',
            executable='async_slam_toolbox_node',
            name='slam_toolbox',
            output='screen',
            parameters=[
                slam_config_path,
                {'use_sim_time': LaunchConfiguration('use_sim_time', default='false')}
            ]
        ),
        
        # 2. Static Transform from odom to base_link (if not provided by odometry)
        # Note: Slam Toolbox can handle the odom->base_link transform if set to publish, 
        # but for a field bot, we often need a base transform.
        Node(
            package='tf2_ros',
            executable='static_transform_publisher',
            name='static_tf_odom_to_base',
            arguments=['--x', '0', '--y', '0', '--z', '0',
                       '--yaw', '0', '--pitch', '0', '--roll', '0',
                       '--frame-id', 'odom', '--child-frame-id', 'base_link']
        )
    ])
