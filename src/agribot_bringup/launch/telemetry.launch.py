import os
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription, DeclareLaunchArgument
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory

def generate_launch_description():
    # ── Launch Arguments ──────────────────────────────────────────────────
    rosbridge_port = LaunchConfiguration('rosbridge_port', default='9090')
    video_port = LaunchConfiguration('video_port', default='8081')
    foxglove_port = LaunchConfiguration('foxglove_port', default='8765')

    ld = LaunchDescription()

    ld.add_action(DeclareLaunchArgument('rosbridge_port', default_value='9090'))
    ld.add_action(DeclareLaunchArgument('video_port', default_value='8081'))
    ld.add_action(DeclareLaunchArgument('foxglove_port', default_value='8765'))

    # 1. ROS Bridge (Websocket for Browser Dashboard)
    # Default Port: 9090
    ld.add_action(IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(get_package_share_directory('rosbridge_server'), 
                         'launch', 'rosbridge_websocket_launch.xml')
        ),
        launch_arguments={
            'port': rosbridge_port,
            'unregister_timeout': '60.0'
        }.items()
    ))

    # 2. Web Video Server (MJPEG Streams for Browser)
    # Standardized Port: 8081 (to avoid conflict with Dashboard on 8080)
    ld.add_action(Node(
        package='web_video_server',
        executable='web_video_server',
        name='web_video_server',
        parameters=[{'port': 8081}], # Hardcoded to 8081 as per senior recommendation
        output='screen'
    ))

    # 3. Foxglove Bridge (Advanced Diagnostics)
    # Standardized Port: 8765
    ld.add_action(Node(
        package='foxglove_bridge',
        executable='foxglove_bridge_node',
        name='foxglove_bridge',
        parameters=[{'port': foxglove_port}],
        output='screen'
    ))

    return ld
