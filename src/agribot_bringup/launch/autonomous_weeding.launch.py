from launch import LaunchDescription
from launch_ros.actions import Node, LifecycleNode
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration

def generate_launch_description():
    return LaunchDescription([
        # Parameters
        DeclareLaunchArgument('model_path', default_value='yolov8n.onnx'),
        DeclareLaunchArgument('conf_threshold', default_value='0.85'),
        
        # Perception Lifecycle Node
        LifecycleNode(
            package='agribot_perception',
            executable='perception_node',
            name='perception_node',
            namespace='',
            output='screen',
            parameters=[{
                'model_path': LaunchConfiguration('model_path'),
                'conf_threshold': LaunchConfiguration('conf_threshold'),
                'max_fps': 5.0
            }]
        ),
        
        # Mode Manager
        Node(
            package='agribot_detection_manager',
            executable='mode_manager',
            name='mode_manager',
            output='screen'
        ),
        
        # Row Detector (Lightweight Mapping)
        Node(
            package='agribot_mapping',
            executable='row_detector',
            name='row_detector',
            output='screen'
        ),
        
        # Latency Compensated Actuation
        Node(
            package='agribot_actuation',
            executable='latency_compensated_sprayer',
            name='latency_compensated_sprayer',
            output='screen',
            parameters=[{'system_latency_ms': 200.0}]
        )
    ])
