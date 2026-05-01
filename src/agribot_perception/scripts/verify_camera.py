import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
import time

class CameraValidator(Node):
    def __init__(self):
        super().__init__('camera_validator')
        self.subscription = self.create_subscription(
            Image,
            'image_raw',
            self.listener_callback,
            10)
        self.frame_count = 0
        self.start_time = time.time()
        self.get_logger().info('Camera Validator started. Listening to /image_raw...')

    def listener_callback(self, msg):
        self.frame_count += 1
        elapsed = time.time() - self.start_time
        if elapsed >= 1.0:
            fps = self.frame_count / elapsed
            self.get_logger().info(f'Resolution: {msg.width}x{msg.height} | Encoding: {msg.encoding} | FPS: {fps:.2f}')
            self.frame_count = 0
            self.start_time = time.time()

if __name__ == '__main__':
    rclpy.init()
    node = CameraValidator()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    node.destroy_node()
    rclpy.shutdown()
