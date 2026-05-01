import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from std_msgs.msg import String
import serial
import time

class MotorBridge(Node):
    def __init__(self):
        super().__init__('motor_bridge')
        
        # Parameters
        self.declare_parameter('port', '/dev/ttyUSB1') # Typically USB1 if LiDAR is USB0
        self.declare_parameter('baud', 9600)
        
        port = self.get_parameter('port').value
        baud = self.get_parameter('baud').value
        
        try:
            self.ser = serial.Serial(port, baud, timeout=0.1)
            self.get_logger().info(f"Connected to Arduino on {port}")
        except Exception as e:
            self.get_logger().error(f"Failed to connect to Arduino: {e}")
            self.ser = None

        # Subscribers
        self.subscription = self.create_subscription(
            Twist,
            '/cmd_vel',
            self.cmd_vel_callback,
            10)
            
        # Publishers (Feedback)
        self.feedback_pub = self.create_publisher(String, '/motor_feedback', 10)
        
        # Timer for reading serial feedback
        self.timer = self.create_timer(0.1, self.read_serial)

    def cmd_vel_callback(self, msg):
        if not self.ser:
            return

        linear = msg.linear.x
        angular = msg.angular.z
        
        speed = int(abs(linear) * 255) # Scale 0.0-1.0 to 0-255
        speed = min(speed, 255)
        
        command = "S"
        if linear > 0.1:
            command = f"F:{speed}"
        elif linear < -0.1:
            command = f"B:{speed}"
        elif angular > 0.1:
            command = f"R:{speed}" # Turning right
        elif angular < -0.1:
            command = f"L:{speed}" # Turning left
        else:
            command = "S"

        self.ser.write(f"{command}\n".encode())
        self.get_logger().info(f"Sent: {command}")

    def read_serial(self):
        if self.ser and self.ser.in_waiting > 0:
            try:
                line = self.ser.readline().decode('utf-8').strip()
                if line:
                    msg = String()
                    msg.data = line
                    self.feedback_pub.publish(msg)
                    self.get_logger().info(f"Feedback: {line}")
            except Exception as e:
                self.get_logger().warn(f"Serial read error: {e}")

def main(args=None):
    rclpy.init(args=args)
    node = MotorBridge()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()
