import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist, TransformStamped, Quaternion
from nav_msgs.msg import Odometry
from std_msgs.msg import String
import tf2_ros
import serial
import time
import math

class MotorBridge(Node):
    def __init__(self):
        super().__init__('motor_bridge')
        
        # Physical Parameters
        self.declare_parameter('port', '/dev/ttyUSB1')
        self.declare_parameter('baud', 115200)
        self.declare_parameter('wheel_radius', 0.025)
        self.declare_parameter('wheel_base', 0.22)
        self.declare_parameter('encoder_cpr', 716)
        
        port = self.get_parameter('port').value
        baud = self.get_parameter('baud').value
        self.R = self.get_parameter('wheel_radius').value
        self.L = self.get_parameter('wheel_base').value
        self.CPR = self.get_parameter('encoder_cpr').value
        
        # State Variables
        self.x = 0.0
        self.y = 0.0
        self.th = 0.0
        self.last_l_ticks = 0
        self.last_r_ticks = 0
        self.last_time = self.get_clock().now()
        self.initialized = False

        try:
            self.ser = serial.Serial(port, baud, timeout=0.1)
            self.get_logger().info(f"Connected to Arduino on {port} at {baud} baud")
        except Exception as e:
            self.get_logger().error(f"Failed to connect to Arduino: {e}")
            self.ser = None

        # ROS Infrastructure
        self.tf_broadcaster = tf2_ros.TransformBroadcaster(self)
        self.odom_pub = self.create_publisher(Odometry, '/odom', 10)
        self.feedback_pub = self.create_publisher(String, '/motor_feedback', 10)
        
        self.subscription = self.create_subscription(
            Twist, '/cmd_vel', self.cmd_vel_callback, 10)
            
        self.timer = self.create_timer(0.033, self.read_serial) # ~30Hz (PID_RATE)

    def cmd_vel_callback(self, msg):
        if not self.ser: return
        
        linear = msg.linear.x
        angular = msg.angular.z
        
        # Simple mapping for basic firmware (ideally firmware should take m/s)
        speed = int(abs(linear) * 255)
        speed = min(speed, 255)
        
        command = "S"
        if linear > 0.05: command = f"F:{speed}"
        elif linear < -0.05: command = f"B:{speed}"
        elif angular > 0.1: command = f"R:{speed}"
        elif angular < -0.1: command = f"L:{speed}"
        
        self.ser.write(f"{command}\n".encode())

    def read_serial(self):
        if not self.ser or self.ser.in_waiting == 0: return
        
        try:
            line = self.ser.readline().decode('utf-8', errors='ignore').strip()
            if not line: return
            
            # Handle Discovery/Config messages
            if "CONFIG:" in line or "STATUS:READY" in line:
                self.get_logger().info(f"Hardware Profile Detected: {line}")
                return

            if "L_ENC:" not in line: return
            
            # Parse line: SPEED:0,DIST:25,CURR:0.00,L_ENC:123,R_ENC:456
            parts = {p.split(':')[0]: p.split(':')[1] for p in line.split(',') if ':' in p}
            
            l_ticks = int(parts.get('L_ENC', 0))
            r_ticks = int(parts.get('R_ENC', 0))
            
            if not self.initialized:
                self.last_l_ticks = l_ticks
                self.last_r_ticks = r_ticks
                self.initialized = True
                return

            current_time = self.get_clock().now()
            dt = (current_time - self.last_time).nanoseconds / 1e9
            
            # Calculate distance per wheel
            d_l = (l_ticks - self.last_l_ticks) * (2 * math.pi * self.R / self.CPR)
            d_r = (r_ticks - self.last_r_ticks) * (2 * math.pi * self.R / self.CPR)
            
            # Distance and rotation
            d_c = (d_l + d_r) / 2.0
            d_th = (d_r - d_l) / self.L
            
            # Update Pose
            self.x += d_c * math.cos(self.th + d_th/2.0)
            self.y += d_c * math.sin(self.th + d_th/2.0)
            self.th += d_th
            
            # Publish Odom & TF
            self.publish_odom(current_time, d_c/dt if dt>0 else 0.0, d_th/dt if dt>0 else 0.0)
            
            self.last_l_ticks = l_ticks
            self.last_r_ticks = r_ticks
            self.last_time = current_time
            
        except Exception as e:
            self.get_logger().warn(f"Odom Error: {e}")

    def publish_odom(self, time, v, w):
        q = self.euler_to_quaternion(0, 0, self.th)
        
        # TF
        t = TransformStamped()
        t.header.stamp = time.to_msg()
        t.header.frame_id = 'odom'
        t.child_frame_id = 'base_link'
        t.transform.translation.x = self.x
        t.transform.translation.y = self.y
        t.transform.rotation = q
        self.tf_broadcaster.sendTransform(t)
        
        # Odom Msg
        odom = Odometry()
        odom.header.stamp = time.to_msg()
        odom.header.frame_id = 'odom'
        odom.child_frame_id = 'base_link'
        odom.pose.pose.position.x = self.x
        odom.pose.pose.position.y = self.y
        odom.pose.pose.orientation = q
        odom.twist.twist.linear.x = v
        odom.twist.twist.angular.z = w
        self.odom_pub.publish(odom)

    def euler_to_quaternion(self, roll, pitch, yaw):
        qx = math.sin(roll/2) * math.cos(pitch/2) * math.cos(yaw/2) - math.cos(roll/2) * math.sin(pitch/2) * math.sin(yaw/2)
        qy = math.cos(roll/2) * math.sin(pitch/2) * math.cos(yaw/2) + math.sin(roll/2) * math.cos(pitch/2) * math.sin(yaw/2)
        qz = math.cos(roll/2) * math.cos(pitch/2) * math.sin(yaw/2) - math.sin(roll/2) * math.sin(pitch/2) * math.cos(yaw/2)
        qw = math.cos(roll/2) * math.cos(pitch/2) * math.cos(yaw/2) + math.sin(roll/2) * math.sin(pitch/2) * math.sin(yaw/2)
        return Quaternion(x=qx, y=qy, z=qz, w=qw)

def main(args=None):
    rclpy.init(args=args)
    node = MotorBridge()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()
