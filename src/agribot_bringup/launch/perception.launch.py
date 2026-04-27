from launch import LaunchDescription
from launch_ros.actions import Node, LifecycleNode
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration

def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument('model_path', default_value='src/agribot_perception/models/yolov8n.onnx'),
        DeclareLaunchArgument('conf_threshold', default_value='0.85'),
        
        # USB Camera Node
        Node(
            package='usb_cam',
            executable='usb_cam_node_exe',
            name='usb_cam',
            parameters=[{
                'video_device': '/dev/video0', 
                'image_width': 640, 
                'image_height': 480,
                'pixel_format': 'yuyv'
            }]
        ),
        
        # RPi5 Optimized Perception Node (Lifecycle)
        LifecycleNode(
            package='agribot_perception',
            executable='perception_node',
            name='perception_node',
            namespace='',
            output='screen',
            parameters=[{
                'model_path': LaunchConfiguration('model_path'),
                'conf_threshold': LaunchConfiguration('conf_threshold'),
                'input_width': 640,
                'input_height': 640,
                'max_fps': 5.0
            }]
        )
    ])
