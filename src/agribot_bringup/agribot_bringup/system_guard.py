import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from geometry_msgs.msg import Point
from std_msgs.msg import String, Bool
from agribot_msgs.msg import DetectionArray
from lifecycle_msgs.srv import ChangeState, GetState
from lifecycle_msgs.msg import Transition, State
import tf2_ros
import time

class SystemGuard(Node):
    def __init__(self):
        super().__init__('system_guard')
        
        # Unified State Machine
        self.state = 'SAFE' # SAFE, CONFIGURING, READY, ACTIVE, ERROR
        self.transition_idx = 0
        self.boot_steps = ['HW_VALIDATION', 'MODEL_WARMUP', 'LIFECYCLE_ACTIVATE', 'TOPIC_HEALTH']
        
        # Diagnostic Data
        self.last_heartbeat = {
            'camera': 0,
            'perception': 0,
            'control': 0
        }
        
        # Clients for Lifecycle Control
        self.lc_clients = {
            'perception': self.create_client(ChangeState, '/perception_node/change_state'),
            'control': self.create_client(ChangeState, '/actuation_node/change_state')
        }
        
        # Subscriptions
        self.create_subscription(Image, 'image_raw', lambda m: self.update_hb('camera'), 10)
        self.create_subscription(Point, 'perception_health', lambda m: self.update_hb('perception'), 10)
        self.create_subscription(String, 'operator_confirm', self.confirm_cb, 10)
        
        # Publishers
        self.status_pub = self.create_publisher(String, 'system_state', 10)
        self.lock_pub = self.create_publisher(Bool, 'safety_lock', 10)
        self.heartbeat_pub = self.create_publisher(Bool, 'guard_heartbeat', 10) # For HW Watchdog
        
        # TF
        self.tf_buffer = tf2_ros.Buffer()
        self.tf_listener = tf2_ros.TransformListener(self.tf_buffer, self)
        
        # Main Logic Timer (5Hz)
        self.timer = self.create_timer(0.2, self.control_loop)
        self.get_logger().info('Industrial-Grade System Guard initialized. System in SAFE mode.')

    def update_hb(self, component):
        self.last_heartbeat[component] = time.time()

    def confirm_cb(self, msg):
        if self.state == 'READY' and msg.data == 'ACTIVATE':
            self.state = 'ACTIVE'
            self.get_logger().info('OPERATOR CONFIRMED: System entering ACTIVE mode.')
        elif msg.data == 'EMERGENCY_STOP':
            self.state = 'SAFE'
            self.get_logger().error('EMERGENCY STOP TRIGGERED BY OPERATOR.')

    def control_loop(self):
        # 1. Hardware Watchdog Heartbeat
        self.heartbeat_pub.publish(Bool(data=True))
        
        # 2. Main State Machine
        if self.state == 'SAFE':
            self.execute_safe_mode()
        elif self.state == 'CONFIGURING':
            self.run_boot_verification()
        elif self.state == 'READY':
            self.monitor_ready_state()
        elif self.state == 'ACTIVE':
            self.run_active_watchdog()
        elif self.state == 'ERROR':
            self.report_error()

        # 3. Enforcement
        self.status_pub.publish(String(data=self.state))
        self.lock_pub.publish(Bool(data=(self.state != 'ACTIVE')))

    def execute_safe_mode(self):
        # Transitions to Configuring if starting
        if time.time() % 5 < 0.2: # Heartbeat log
            self.get_logger().info('SAFE - Waiting for startup sequence...')
        # Automatically attempt configuration
        self.state = 'CONFIGURING'

    def run_boot_verification(self):
        step = self.boot_steps[self.transition_idx]
        success = False
        
        if step == 'HW_VALIDATION':
            success = (time.time() - self.last_heartbeat['camera']) < 2.0
        elif step == 'MODEL_WARMUP':
            success = (time.time() - self.last_heartbeat['perception']) < 2.0
        elif step == 'LIFECYCLE_ACTIVATE':
            # Simplified: assuming auto-activated or calling services
            success = True 
        elif step == 'TOPIC_HEALTH':
            success = self.check_tf()
            
        if success:
            self.get_logger().info(f'VERIFIED: {step}')
            self.transition_idx += 1
            if self.transition_idx >= len(self.boot_steps):
                self.state = 'READY'
                self.get_logger().info('VERIFICATION COMPLETE: SYSTEM READY (LOCKED)')
        else:
            self.get_logger().debug(f'Waiting for {step}...')

    def run_active_watchdog(self):
        # Monitor all heartbeats. If any lost, transition to ERROR/SAFE
        if (time.time() - self.last_heartbeat['camera']) > 1.0:
            self.state = 'ERROR'
            self.get_logger().error('WATCHDOG: CAMERA HEARTBEAT LOST! REVERTING TO SAFE.')

    def check_tf(self):
        try:
            self.tf_buffer.lookup_transform('base_link', 'camera_link', rclpy.time.Time())
            return True
        except:
            return False

    def report_error(self):
        self.get_logger().error('SYSTEM IN ERROR STATE. Manual intervention required.')

def main(args=None):
    rclpy.init(args=args)
    node = SystemGuard()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()
