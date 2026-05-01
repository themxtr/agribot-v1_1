from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import LifecycleNode, Node


def generate_launch_description():
    return LaunchDescription(
        [
            DeclareLaunchArgument(
                'model_path',
                default_value='C:/Users/FRIDAY/runs/detect/runs/precision_agri/yolov8_p2_simam_ema-4/weights/best.pt',
            ),
            DeclareLaunchArgument('conf_threshold', default_value='0.25'),
            LifecycleNode(
                package='agribot_perception',
                executable='perception_node',
                name='perception_node',
                output='screen',
                parameters=[
                    {
                        'model_path': LaunchConfiguration('model_path'),
                        'conf_threshold': LaunchConfiguration('conf_threshold'),
                        'slice_size': 640,
                        'overlap_ratio': 0.2,
                        'nms_iou_threshold': 0.75,
                        'max_fps': 5.0,
                        'show_window': False,
                        'annotated_topic': 'image_annotated',
                    }
                ],
            ),
            Node(
                package='agribot_detection_manager',
                executable='mode_manager',
                name='mode_manager',
                output='screen',
            ),
            Node(
                package='agribot_mapping',
                executable='row_detector',
                name='row_detector',
                output='screen',
            ),
            Node(
                package='agribot_actuation',
                executable='latency_compensated_sprayer',
                name='latency_compensated_sprayer',
                output='screen',
                parameters=[{'system_latency_ms': 200.0}],
            ),
            Node(
                package='agribot_bringup',
                executable='system_guard',
                name='system_guard',
                output='screen',
            ),
        ]
    )
