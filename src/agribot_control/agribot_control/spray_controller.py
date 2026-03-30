import rclpy
from rclpy.node import Node
from agribot_msgs.msg import DetectionArray
from std_msgs.msg import Bool, String
import time

class SprayController(Node):
    def __init__(self):
        super().__init__('spray_controller')
        
        # Parameters
        self.declare_parameter('spray_threshold_y', 300) # Pixel threshold or distance
        self.declare_parameter('target_label', 'weed')
        
        self.target_label = self.get_parameter('target_label').get_parameter_value().string_value
        self.spray_threshold_y = self.get_parameter('spray_threshold_y').get_parameter_value().integer_value
        
        # Subscribers
        self.subscription = self.create_subscription(
            DetectionArray,
            'detections',
            self.detection_callback,
            10)
            
        # Publishers
        self.spray_pub = self.create_publisher(Bool, 'spray_actuator', 10)
        self.status_pub = self.create_publisher(String, 'bot_status', 10)
        
        self.get_logger().info('Spray Controller Initialized')
        self.last_spray_time = 0

    def detection_callback(self, msg):
        for detection in msg.detections:
            if self.target_label in detection.label.lower():
                # Logic: If weed is in the "strike zone" (e.g. bottom half of image, center)
                # This assumes camera is looking down/forward at a fixed angle
                # In a real system, you'd transform this to world coordinates using the map
                
                self.get_logger().info(f'Weed detected at ({detection.x}, {detection.y})')
                
                # Check if it's close enough to the front (y threshold)
                if detection.y > self.spray_threshold_y:
                    self.trigger_spray()

    def trigger_spray(self):
        # Prevent rapid double-spraying
        current_time = time.time()
        if current_time - self.last_spray_time < 2.0:
            return
            
        self.get_logger().info('!!! TRIGGERING SPRAY !!!')
        
        # Publish spray command
        msg = Bool()
        msg.data = True
        self.spray_pub.publish(msg)
        
        # Status update
        status = String()
        status.data = "Exterminating weed..."
        self.status_pub.publish(status)
        
        # Reset after a short duration (simulate valve open/close)
        time.sleep(0.5)
        msg.data = False
        self.spray_pub.publish(msg)
        
        self.last_spray_time = current_time

def main(args=None):
    rclpy.init(args=args)
    node = SprayController()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()
