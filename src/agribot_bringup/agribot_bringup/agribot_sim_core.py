#!/usr/bin/env python3
"""
Agribot v1.1 — Simulation Core (Mock Hardware)
==============================================
Software-in-the-loop mock for all hardware-dependent ROS 2 nodes.
Publishes synthetic sensor data, implements the five-state guard
machine, and supports scenario-driven fault injection for testing
the dashboard and telemetry stack without physical hardware.

Scenarios (set via ROS 2 parameter 'scenario'):
  - "nominal"        : All systems healthy, normal boot sequence.
  - "camera_loss"    : Camera drops out after 15s for 30s, then recovers.
  - "error_recovery" : System enters ERROR after 10s, auto-recovers.
"""

import json
import math
import random
import time
from typing import Optional

import cv2
import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.executors import MultiThreadedExecutor
from rclpy.callback_groups import MutuallyExclusiveCallbackGroup, ReentrantCallbackGroup
from std_msgs.msg import String, Bool
from sensor_msgs.msg import LaserScan, CompressedImage
from geometry_msgs.msg import TwistStamped, Twist, TransformStamped
from tf2_ros import TransformBroadcaster


class AgribotSimCore(Node):
    """Mock hardware node that simulates the full Agribot sensor/actuator stack."""

    def __init__(self) -> None:
        super().__init__('agribot_sim_core')

        self.get_logger().info('Initializing Agribot Simulation Core...')

        # ── ROS 2 Parameters ────────────────────────────────────────────
        self.declare_parameter('scenario', 'nominal')
        self.scenario: str = self.get_parameter('scenario').get_parameter_value().string_value
        self.get_logger().info(f'Scenario: {self.scenario}')

        # ── Internal State Machine ──────────────────────────────────────
        self.states: list[str] = ['SAFE', 'CONFIGURING', 'READY', 'ACTIVE', 'ERROR']
        self.current_state_idx: int = 0
        self.boot_start_time: float = time.time()
        self.is_active: bool = False
        self.current_mode: str = 'NONE'
        self.spray_active: bool = False
        self.spray_timer: int = 0

        # ── Scenario State ──────────────────────────────────────────────
        self.camera_suppressed: bool = False
        self.error_injected: bool = False
        self.scenario_start_time: float = time.time()

        # ── Robot Motion ────────────────────────────────────────────────
        self.pos_x = 0.0
        self.vel_x = 0.0
        self.vel_theta = 0.0
        self.initial_pos = 0.0
        self.max_scan_dist = 5.0
        self.returning = False
        
        # Virtual Field Data
        self.virtual_weeds = [1.5, 3.2, 4.5]
        self.virtual_crops = [0.5, 1.0, 2.0, 2.5, 3.5, 4.0]
        self.detected_points = [] # Memory for weeds
        self.current_target_idx = -1
        self.target_wait_timer = 0

        # ── Callback Groups ─────────────────────────────────────────────
        # Camera encoding is slow; isolate it to prevent blocking other pubs
        self._camera_cb_group = ReentrantCallbackGroup()
        self._default_cb_group = MutuallyExclusiveCallbackGroup()

        # ── Publishers ──────────────────────────────────────────────────
        self.state_pub = self.create_publisher(String, '/system_state', 10)
        self.hw_pub = self.create_publisher(String, '/hw_capabilities', 10)
        self.scan_pub = self.create_publisher(LaserScan, '/scan', 5)
        self.img_pub = self.create_publisher(CompressedImage, '/image_raw/compressed', 5)
        self.odom_pub = self.create_publisher(TwistStamped, '/odom_vel', 10)
        self.tf_broadcaster = TransformBroadcaster(self)
        self.spray_pub = self.create_publisher(Bool, '/spray_active', 10)
        self.det_pub = self.create_publisher(String, '/detections', 10)
        self.event_pub = self.create_publisher(String, '/sim_event', 10)

        # ── Subscribers ─────────────────────────────────────────────────
        # Subscriptions
        self.create_subscription(String, '/set_mode', self._mode_callback, 10)
        self.create_subscription(String, '/operator_confirm', self._confirm_callback, 10)
        self.create_subscription(Twist, '/cmd_vel', self._cmd_vel_callback, 10)

        # ── Timers ──────────────────────────────────────────────────────
        # High-performance timers optimized for low-CPU environments
        self.create_timer(1.0, self.publish_state, callback_group=self._default_cb_group)
        self.create_timer(1.0, self.publish_scan, callback_group=self._default_cb_group)
        self.create_timer(1.0, self.publish_image, callback_group=self._camera_cb_group)
        self.create_timer(0.1, self.publish_odom, callback_group=self._default_cb_group)

        # Scenario driver timer
        self.create_timer(1.0, self._drive_scenario, callback_group=self._default_cb_group)

        self.get_logger().info('Simulation Core Ready. Starting boot sequence...')

    # ── Message Handlers ────────────────────────────────────────────────

    def _cmd_vel_callback(self, msg: Twist) -> None:
        """Allow manual override of the robot."""
        if self.current_mode == 'SAFE':
            return
        self.vel_x = msg.linear.x
        self.vel_theta = msg.angular.z
        self.get_logger().info(f'Manual Override: v={self.vel_x}, w={self.vel_theta}')

    def _confirm_callback(self, msg: String) -> None:
        """Handle operator confirmation (ACTIVATE) from the dashboard."""
        if msg.data == 'ACTIVATE' and self.states[self.current_state_idx] == 'READY':
            self.current_state_idx = 3  # ACTIVE
            self.is_active = True
            self.get_logger().info('System ACTIVATED by operator.')

    def _mode_callback(self, msg: String) -> None:
        """Handle mode changes and reset mission state."""
        new_mode = msg.data.upper()
        if new_mode == self.current_mode: return
        
        self.current_mode = new_mode
        self.get_logger().info(f'Mode changed to: {self.current_mode}')
        
        # Reset mission variables
        self.returning = False
        self.current_target_idx = -1
        self.target_wait_timer = 0
        if new_mode == 'DETECT':
            self.detected_points = [] # Clear memory for new scan
        """Handle operator confirmation (ACTIVATE) from the dashboard."""
        if msg.data == 'ACTIVATE' and self.states[self.current_state_idx] == 'READY':
            self.current_state_idx = 3  # ACTIVE
            self.is_active = True
            self.get_logger().info('System ACTIVATED by operator.')

    def handle_set_mode(self, msg: String) -> None:
        """Handle mode commands from the dashboard."""
        mode = msg.data

        if mode == 'SAFE':
            # Emergency stop — always honoured regardless of active state
            self.current_state_idx = 0
            self.is_active = False
            self.spray_active = False
            self.spray_pub.publish(Bool(data=False))
            self.current_mode = 'SAFE'
            self.get_logger().info('EMERGENCY STOP: System returned to SAFE.')
            return

        if not self.is_active:
            self.get_logger().warn(f'Ignored mode {mode} — System not ACTIVE')
            return

        self.current_mode = mode
        self.get_logger().info(f'Mode set to: {self.current_mode}')

        if mode == 'SPRAY':
            self.spray_active = True
            self.spray_timer = 20  # 2 seconds at 10Hz publish rate
            self.spray_pub.publish(Bool(data=True))

    def handle_cmd_vel(self, msg: Twist) -> None:
        """Update simulation velocity from external commands."""
        self.vel_x = msg.linear.x

    # ── Scenario Driver ─────────────────────────────────────────────────

    def _drive_scenario(self) -> None:
        """Handle scenario-specific fault injections and auto-boot sequence."""
        elapsed = time.time() - self.scenario_start_time
        
        # Auto-boot transition (Accelerated)
        if self.current_state_idx == 0: # SAFE
            if elapsed > 1.0:
                self.current_state_idx = 1 # CONFIGURING
        elif self.current_state_idx == 1: # CONFIGURING
            if elapsed > 3.0:
                self.current_state_idx = 2 # READY

        if self.scenario == 'camera_loss':
            if 15.0 <= elapsed < 45.0 and not self.camera_suppressed:
                self.camera_suppressed = True
                self._publish_event('WARN: camera_loss — feed suppressed for 30s')
                self.get_logger().warn('Scenario: Camera feed suppressed.')
            elif elapsed >= 45.0 and self.camera_suppressed:
                self.camera_suppressed = False
                self._publish_event('INFO: camera_restored')
                self.get_logger().info('Scenario: Camera feed restored.')

        elif self.scenario == 'error_recovery':
            if 10.0 <= elapsed < 15.0 and not self.error_injected:
                self.error_injected = True
                self.current_state_idx = 4  # ERROR
                self.is_active = False
                self._publish_event('ERROR: lidar_heartbeat_lost — entering ERROR state')
                self.get_logger().error('Scenario: ERROR state injected.')
            elif 15.0 <= elapsed < 16.0 and self.error_injected:
                # Begin auto-recovery: ERROR -> SAFE
                self.current_state_idx = 0
                self.error_injected = False
                self.boot_start_time = time.time()  # Reset boot timer
                self._publish_event('INFO: auto_recovery — restarting state machine')
                self.get_logger().info('Scenario: Auto-recovery initiated.')

    def _publish_event(self, text: str) -> None:
        """Publish a simulation event message."""
        self.event_pub.publish(String(data=text))

    # ── Publisher Callbacks ─────────────────────────────────────────────

    def publish_state(self) -> None:
        """Publish system state and hardware capabilities at 1 Hz."""

        state = self.states[self.current_state_idx]
        self.state_pub.publish(String(data=state))

        # Hardware capabilities (adjusted for camera_loss scenario)
        has_camera = not self.camera_suppressed
        hw_msg = String()
        hw_msg.data = json.dumps({
            "has_camera": has_camera,
            "has_lidar": True,
            "has_motor": True
        })
        self.hw_pub.publish(hw_msg)

    def publish_scan(self) -> None:
        """Publish synthetic LiDAR scan at 5 Hz."""
        scan = LaserScan()
        scan.header.stamp = self.get_clock().now().to_msg()
        scan.header.frame_id = 'lidar_link'
        scan.angle_min = 0.0
        scan.angle_max = 2.0 * math.pi
        scan.angle_increment = (2.0 * math.pi) / 360.0
        scan.time_increment = 0.0
        scan.scan_time = 1.0
        scan.range_min = 0.15
        scan.range_max = 12.0

        t = time.time()
        # Fixed World: Straight Crop Rows at Y=1.0 and Y=-1.0
        ranges = []
        for i in range(120):
            angle = i * 3 * scan.angle_increment
            # Simplified ray-casting for two parallel walls
            dist = 12.0
            if math.sin(angle) > 0: # Left wall
                dist = abs(1.0 / (math.sin(angle) + 1e-6))
            elif math.sin(angle) < 0: # Right wall
                dist = abs(-1.0 / (math.sin(angle) + 1e-6))
            ranges.append(min(dist, 12.0))
        scan.ranges = ranges
        scan.angle_increment *= 3 
        self.scan_pub.publish(scan)

    def publish_image(self) -> None:
        """Publish synthetic camera image with YOLO overlays at 5 Hz.

        Runs on a ReentrantCallbackGroup to avoid blocking other publishers
        during the OpenCV encode step (Bug Fix #1).
        """
        # Camera suppressed during camera_loss scenario
        if self.camera_suppressed:
            return

        t_start = time.perf_counter()

        # Generate synthetic crop-row scene
        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        frame[:] = (40, 60, 80)  # Brown earth

        # Crop rows (vertical green stripes)
        for x in [80, 160, 240]:
            cv2.rectangle(frame, (x - 10, 0), (x + 10, 240), (40, 150, 40), -1)

        # Randomised weeds between rows
        rng = random.Random(int(time.time() * 5))
        for _ in range(3):
            wx = rng.randint(25, 295)
            wy = rng.randint(25, 215)
            cv2.circle(frame, (wx, wy), 7, (20, 100, 20), -1)

        # YOLO-style bounding boxes when detecting
        if self.current_mode in ['DETECT', 'SPRAY']:
            for x in [80, 160, 240]:
                cv2.rectangle(frame, (x - 15, 50), (x + 15, 100), (255, 255, 0), 2)
                cv2.putText(frame, 'CROP 0.92', (x - 15, 45),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 0), 1)
            cv2.rectangle(frame, (50, 150), (80, 180), (0, 0, 255), 2)
            cv2.putText(frame, 'WEED 0.75', (50, 145),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 255), 1)

        # Spray indicator overlay
        if self.spray_active:
            cv2.circle(frame, (160, 200), 20, (0, 0, 255), -1)
            cv2.putText(frame, 'SPRAY ACTIVE', (120, 230),
                        cv2.FONT_HERSHEY_DUPLEX, 0.5, (255, 255, 255), 1)
            self.spray_timer -= 1
            if self.spray_timer <= 0:
                self.spray_active = False
                self.spray_pub.publish(Bool(data=True)) # Keep it high during the cycle logic

        # JPEG encode and publish (Bug Fix #2: correct headers)
        _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 30])
        msg = CompressedImage()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = 'camera_link'
        msg.format = 'jpeg'
        msg.data = buffer.tobytes()
        self.img_pub.publish(msg)

        # Performance monitoring
        elapsed_ms = (time.perf_counter() - t_start) * 1000.0
        if elapsed_ms > 150.0:
            self.get_logger().warn(
                f'Camera encode took {elapsed_ms:.1f}ms — consider reducing resolution'
            )

    def publish_detections(self) -> None:
        """Publish mock YOLO detections at ~3 Hz."""
        if self.current_mode not in ['DETECT', 'SPRAY']:
            return
        if self.camera_suppressed:
            return

        rng = random.Random(int(time.time() * 3))
        dets = []
        
        # Check for virtual crops in view
        for crop_x in self.virtual_crops:
            if abs(self.pos_x - crop_x) < 0.5:
                dets.append({
                    "label": "crop",
                    "conf": round(rng.uniform(0.85, 0.98), 2),
                    "bbox": [130, 100, 60, 100]
                })

        # Check for virtual weeds in view
        for weed_x in self.virtual_weeds:
            if abs(self.pos_x - weed_x) < 0.5:
                dets.append({
                    "label": "weed",
                    "conf": round(rng.uniform(0.70, 0.90), 2),
                    "bbox": [100, 200, 60, 60]
                })

        self.det_pub.publish(String(data=json.dumps(dets)))

    def publish_odom(self) -> None:
        """High-precision Mission Orchestrator (10Hz)."""
        dt = 0.1
        
        if self.current_mode == 'SCAN':
            if not self.returning:
                if self.pos_x < self.max_scan_dist: self.vel_x = 0.3
                else: self.returning = True
            else:
                if self.pos_x > 0.05: self.vel_x = -0.3
                else:
                    self.vel_x = 0.0
                    self.current_mode = 'READY'
                    self.get_logger().info('SCAN COMPLETE. System in Standby.')

        elif self.current_mode == 'DETECT':
            if not self.returning:
                if self.pos_x < self.max_scan_dist:
                    self.vel_x = 0.2
                    # Record weeds as we pass them
                    for wx in self.virtual_weeds:
                        if abs(self.pos_x - wx) < 0.1 and wx not in self.detected_points:
                            self.detected_points.append(wx)
                            self.get_logger().info(f'POINT MARKED: Weed at {wx}m')
                else: self.returning = True
            else:
                if self.pos_x > 0.05: self.vel_x = -0.3
                else:
                    self.vel_x = 0.0
                    self.current_mode = 'READY'
                    self.get_logger().info(f'DETECTION COMPLETE. {len(self.detected_points)} points saved.')

        elif self.current_mode == 'SPRAY':
            if not self.detected_points:
                self.get_logger().warn('No points in memory! Returning to home.')
                self.current_mode = 'SCAN' # Fallback
                return

            if self.current_target_idx == -1: self.current_target_idx = 0
            
            if self.current_target_idx < len(self.detected_points):
                target_x = self.detected_points[self.current_target_idx]
                if abs(self.pos_x - target_x) > 0.1:
                    self.vel_x = 0.2 if self.pos_x < target_x else -0.2
                else:
                    self.vel_x = 0.0
                    if self.target_wait_timer == 0:
                        self.get_logger().info(f'SPRAYING POINT {self.current_target_idx + 1}...')
                        self.spray_active = True
                    self.target_wait_timer += 1
                    if self.target_wait_timer > 20: # 2 seconds
                        self.target_wait_timer = 0
                        self.spray_active = False
                        self.current_target_idx += 1
            else:
                # Mission finished, return home
                if self.pos_x > 0.05: self.vel_x = -0.3
                else:
                    self.vel_x = 0.0
                    self.current_mode = 'READY'
                    self.get_logger().info('SPRAY MISSION COMPLETE.')

        elif self.current_mode == 'SAFE':
            self.vel_x = 0.0
            self.vel_theta = 0.0

        # Update Position
        self.pos_x += self.vel_x * dt
        
        # 3. Publish Message
        msg = TwistStamped()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = 'odom'
        msg.twist.linear.x = self.vel_x
        msg.twist.angular.z = 0.0
        self.odom_pub.publish(msg)

        # Broadcast odom -> base_footprint transform
        t = TransformStamped()
        t.header.stamp = self.get_clock().now().to_msg()
        t.header.frame_id = 'odom'
        t.child_frame_id = 'base_footprint'
        t.transform.translation.x = self.pos_x
        t.transform.translation.y = 0.0
        t.transform.translation.z = 0.0
        t.transform.rotation.x = 0.0
        t.transform.rotation.y = 0.0
        t.transform.rotation.z = 0.0
        t.transform.rotation.w = 1.0
        self.tf_broadcaster.sendTransform(t)


def main() -> None:
    """Entry point with MultiThreadedExecutor (Bug Fix #1)."""
    rclpy.init()
    node = AgribotSimCore()
    executor = MultiThreadedExecutor(num_threads=4)
    executor.add_node(node)
    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
