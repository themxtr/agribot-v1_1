import os
from launch import LaunchDescription
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory

def generate_launch_description():
    ld = LaunchDescription()

    # 1. RPLidar Node (sllidar_ros2)
    # Assuming the user has sllidar_ros2 installed
    lidar_node = Node(
        package='sllidar_ros2',
        executable='sllidar_node',
        name='sllidar_node',
        parameters=[{'channel_type': 'serial', 'serial_port': '/dev/ttyUSB0', 'serial_baudrate': 115200}]
    )

    # 2. Hector SLAM Node
    # Assuming hector_slam ROS2 port is used
    hector_slam_node = Node(
        package='hector_mapping',
        executable='hector_mapping',
        name='hector_mapping',
        parameters=[{
            'map_size': 2048,
            'map_resolution': 0.05,
            'scan_topic': 'scan',
            'base_frame': 'base_link',
            'map_frame': 'map',
            'odom_frame': 'base_link' # Hector SLAM doesn't strictly need odom
        }]
    )

    # 3. Camera Node (usb_cam)
    camera_node = Node(
        package='usb_cam',
        executable='usb_cam_node_exe',
        name='usb_cam',
        parameters=[{'video_device': '/dev/video0', 'image_width': 640, 'image_height': 480}]
    )

    # 4. Perception Node (Agribot)
    perception_node = Node(
        package='agribot_perception',
        executable='detection_node',
        name='detection_node',
        parameters=[{'model_path': 'yolov8n.pt', 'confidence_threshold': 0.5}]
    )

    # 5. Control Node (Agribot)
    control_node = Node(
        package='agribot_control',
        executable='spray_controller',
        name='spray_controller',
        parameters=[{'spray_threshold_y': 400, 'target_label': 'weed'}]
    )

    ld.add_action(lidar_node)
    ld.add_action(hector_slam_node)
    ld.add_action(camera_node)
    ld.add_action(perception_node)
    ld.add_action(control_node)

    return ld
