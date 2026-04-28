"""
system_guard — Fault-tolerant safety monitor for Agribot v1.1.

Adapts its boot verification sequence dynamically based on which hardware
was detected at launch time.  The guard will proceed to READY even if
camera/perception are absent (degraded SCAN-only mode).

Parameters (set by main_launch.py):
    hw_has_camera  (bool)  — camera + perception pipeline is running
    hw_has_lidar   (bool)  — LiDAR node is running
    hw_has_motor   (bool)  — motor bridge is running
"""

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image, LaserScan
from geometry_msgs.msg import Point
from std_msgs.msg import String, Bool
from lifecycle_msgs.srv import ChangeState
from lifecycle_msgs.msg import Transition
import tf2_ros
import time


class SystemGuard(Node):
    def __init__(self):
        super().__init__('system_guard')

        # ── Hardware capability parameters (set by launch file) ──────────
        self.declare_parameter('hw_has_camera', False)
        self.declare_parameter('hw_has_lidar', False)
        self.declare_parameter('hw_has_motor', False)

        self.hw_camera = self.get_parameter('hw_has_camera').value
        self.hw_lidar = self.get_parameter('hw_has_lidar').value
        self.hw_motor = self.get_parameter('hw_has_motor').value

        # ── Build dynamic boot sequence based on detected hardware ───────
        self.boot_steps = []
        if self.hw_lidar:
            self.boot_steps.append('LIDAR_HEALTH')
        if self.hw_camera:
            self.boot_steps.append('CAMERA_HEALTH')
            self.boot_steps.append('MODEL_WARMUP')
            self.boot_steps.append('LIFECYCLE_ACTIVATE')
        self.boot_steps.append('TF_HEALTH')  # Always check TF tree

        # ── State machine ────────────────────────────────────────────────
        self.state = 'SAFE'
        self.transition_idx = 0

        # ── Heartbeats ───────────────────────────────────────────────────
        self.last_heartbeat = {
            'camera': 0.0,
            'perception': 0.0,
            'lidar': 0.0,
        }

        # ── Lifecycle clients (only if camera pipeline is present) ───────
        self.lc_clients = {}
        if self.hw_camera:
            self.lc_clients['perception'] = self.create_client(
                ChangeState, '/perception_node/change_state')

        # ── Subscriptions (conditional) ──────────────────────────────────
        if self.hw_camera:
            self.create_subscription(
                Image, 'image_raw', lambda m: self.update_hb('camera'), 10)
            self.create_subscription(
                Point, 'perception_health', lambda m: self.update_hb('perception'), 10)
        if self.hw_lidar:
            self.create_subscription(
                LaserScan, 'scan', lambda m: self.update_hb('lidar'), 10)

        self.create_subscription(String, 'operator_confirm', self.confirm_cb, 10)

        # ── Publishers ───────────────────────────────────────────────────
        self.status_pub = self.create_publisher(String, 'system_state', 10)
        self.lock_pub = self.create_publisher(Bool, 'safety_lock', 10)
        self.heartbeat_pub = self.create_publisher(Bool, 'guard_heartbeat', 10)
        self.hw_report_pub = self.create_publisher(String, 'hw_capabilities', 10)

        # ── TF ───────────────────────────────────────────────────────────
        self.tf_buffer = tf2_ros.Buffer()
        self.tf_listener = tf2_ros.TransformListener(self.tf_buffer, self)

        # ── Main timer (5 Hz) ────────────────────────────────────────────
        self.timer = self.create_timer(0.2, self.control_loop)
        self._boot_logged = False
        self._log_hw_inventory()

    # ─────────────────────────────────────────────────────────────────────
    # Logging
    # ─────────────────────────────────────────────────────────────────────
    def _log_hw_inventory(self):
        mode = 'FULL' if self.hw_camera else 'SCAN-ONLY (no CV)'
        self.get_logger().info('╔══════════════════════════════════════╗')
        self.get_logger().info('║    SYSTEM GUARD — HW INVENTORY      ║')
        self.get_logger().info('╠══════════════════════════════════════╣')
        self.get_logger().info(f'║  Camera  : {"✅ PRESENT" if self.hw_camera else "❌ ABSENT "}           ║')
        self.get_logger().info(f'║  LiDAR   : {"✅ PRESENT" if self.hw_lidar else "❌ ABSENT "}           ║')
        self.get_logger().info(f'║  Motor   : {"✅ PRESENT" if self.hw_motor else "❌ ABSENT "}           ║')
        self.get_logger().info(f'║  Mode    : {mode:<27}║')
        self.get_logger().info(f'║  Steps   : {len(self.boot_steps)} verification steps       ║')
        self.get_logger().info('╚══════════════════════════════════════╝')

    # ─────────────────────────────────────────────────────────────────────
    # Heartbeat helpers
    # ─────────────────────────────────────────────────────────────────────
    def update_hb(self, component):
        self.last_heartbeat[component] = time.time()

    def hb_alive(self, component, timeout=3.0):
        return (time.time() - self.last_heartbeat[component]) < timeout

    # ─────────────────────────────────────────────────────────────────────
    # Operator confirmation
    # ─────────────────────────────────────────────────────────────────────
    def confirm_cb(self, msg):
        if self.state == 'READY' and msg.data == 'ACTIVATE':
            self.state = 'ACTIVE'
            self.get_logger().info('OPERATOR CONFIRMED: System entering ACTIVE mode.')
        elif msg.data == 'EMERGENCY_STOP':
            self.state = 'SAFE'
            self.transition_idx = 0
            self.get_logger().error('EMERGENCY STOP TRIGGERED BY OPERATOR.')

    # ─────────────────────────────────────────────────────────────────────
    # Main loop
    # ─────────────────────────────────────────────────────────────────────
    def control_loop(self):
        self.heartbeat_pub.publish(Bool(data=True))

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

        self.status_pub.publish(String(data=self.state))
        self.lock_pub.publish(Bool(data=(self.state != 'ACTIVE')))

        # Publish capabilities summary
        caps = []
        if self.hw_camera:
            caps.append('camera')
        if self.hw_lidar:
            caps.append('lidar')
        if self.hw_motor:
            caps.append('motor')
        self.hw_report_pub.publish(String(data=','.join(caps) if caps else 'none'))

    # ─────────────────────────────────────────────────────────────────────
    # State handlers
    # ─────────────────────────────────────────────────────────────────────
    def execute_safe_mode(self):
        if not self._boot_logged:
            self.get_logger().info('SAFE → entering CONFIGURING...')
            self._boot_logged = True
        self.state = 'CONFIGURING'

    def run_boot_verification(self):
        if self.transition_idx >= len(self.boot_steps):
            self.state = 'READY'
            mode = 'FULL (Scan + Detect + Spray)' if self.hw_camera else 'SCAN-ONLY (LiDAR mapping)'
            self.get_logger().info(f'✅ VERIFICATION COMPLETE — Mode: {mode} — SYSTEM READY (LOCKED)')
            return

        step = self.boot_steps[self.transition_idx]
        success = False

        if step == 'LIDAR_HEALTH':
            success = self.hb_alive('lidar', timeout=5.0)
        elif step == 'CAMERA_HEALTH':
            success = self.hb_alive('camera', timeout=5.0)
        elif step == 'MODEL_WARMUP':
            success = self.hb_alive('perception', timeout=5.0)
        elif step == 'LIFECYCLE_ACTIVATE':
            success = self.transition_node('perception', Transition.TRANSITION_CONFIGURE)
            if success:
                success = self.transition_node('perception', Transition.TRANSITION_ACTIVATE)
        elif step == 'TF_HEALTH':
            success = self.check_tf()

        if success:
            self.get_logger().info(f'✅ VERIFIED: {step}')
            self.transition_idx += 1
        else:
            self.get_logger().debug(f'⏳ Waiting for {step}...')

    def transition_node(self, node_key, transition_id):
        if node_key not in self.lc_clients:
            return False
        client = self.lc_clients[node_key]
        if not client.wait_for_service(timeout_sec=0.1):
            return False
        request = ChangeState.Request()
        request.transition.id = transition_id
        client.call_async(request)
        return True

    def monitor_ready_state(self):
        pass  # Waiting for operator_confirm

    def run_active_watchdog(self):
        """Monitor active heartbeats.  Only trigger ERROR for hardware that
        was detected at boot — do NOT error on absent optional hardware."""
        if self.hw_lidar and not self.hb_alive('lidar', timeout=2.0):
            self.state = 'ERROR'
            self.get_logger().error('WATCHDOG: LiDAR HEARTBEAT LOST! REVERTING TO SAFE.')
        if self.hw_camera and not self.hb_alive('camera', timeout=2.0):
            self.get_logger().warn('WATCHDOG: Camera heartbeat lost — perception degraded.')
            # Camera loss is a warning, not a fatal error. LiDAR keeps working.

    def check_tf(self):
        """Verify TF tree.  Check base_link→laser if LiDAR present,
        or base_link→camera_link if camera present."""
        try:
            if self.hw_lidar:
                self.tf_buffer.lookup_transform('base_link', 'laser', rclpy.time.Time())
            elif self.hw_camera:
                self.tf_buffer.lookup_transform('base_link', 'camera_link', rclpy.time.Time())
            else:
                return True  # No sensors — TF trivially OK
            return True
        except Exception:
            return False

    def report_error(self):
        self.get_logger().error('SYSTEM IN ERROR STATE. Attempting auto-recovery to SAFE...')
        self.state = 'SAFE'
        self.transition_idx = 0
        self._boot_logged = False


def main(args=None):
    rclpy.init(args=args)
    node = SystemGuard()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
