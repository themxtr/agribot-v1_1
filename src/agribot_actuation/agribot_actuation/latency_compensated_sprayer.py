import rclpy
from rclpy.action import ActionServer
from rclpy.node import Node
from agribot_msgs.action import SprayAction
from nav_msgs.msg import Odometry
from std_msgs.msg import Bool
import time
import math

class SprayerActionServer(Node):
    def __init__(self):
        super().__init__('latency_compensated_sprayer')
        self._action_server = ActionServer(
            self,
            SprayAction,
            'spray_weed',
            self.execute_callback)
        
        self.odom_sub = self.create_subscription(Odometry, 'odom', self.odom_cb, 10)
        self.safety_sub = self.create_subscription(Bool, 'safety_lock', self.lock_cb, 10)
        self.current_velocity = 0.0
        self.is_locked = True
        self.declare_parameter('system_latency_ms', 200.0) # Default 200ms
        
        self.get_logger().info('Latency Compensated Sprayer node started.')

    def odom_cb(self, msg):
        self.current_velocity = msg.twist.twist.linear.x

    def lock_cb(self, msg):
        self.is_locked = msg.data

    async def execute_callback(self, goal_handle):
        if self.is_locked:
            self.get_logger().warn('SPRAY ATTEMPTED WHILE LOCKED! Aborting.')
            goal_handle.abort()
            return SprayAction.Result(success=False, message="Locked")

        self.get_logger().info('Executing spray goal...')
        feedback_msg = SprayAction.Feedback()
        
        # Target position relative to robot (e.g. from camera-to-nozzle transform)
        target_pose = goal_handle.request.target_pose
        latency_comp = self.get_parameter('system_latency_ms').value
        
        # Simple 1D prediction: spray nozzle is at x=0 (relative to robot)
        # Weed is at target_pose.pose.position.x
        dist_to_nozzle = target_pose.pose.position.x 
        
        while dist_to_nozzle > 0.05: # While target is still in front
            if self.current_velocity > 0.01:
                time_to_trigger = (dist_to_nozzle / self.current_velocity) - (latency_comp / 1000.0)
                
                feedback_msg.distance_to_target = dist_to_nozzle
                feedback_msg.time_to_trigger = time_to_trigger
                goal_handle.publish_feedback(feedback_msg)
                
                if time_to_trigger <= 0:
                    self.get_logger().info('TRIGGERING SPRAY!')
                    # Actual hardware trigger logic here
                    break
            
            time.sleep(0.01)
            # Update distance (simplified, usually done via TF)
            # dist_to_nozzle -= self.current_velocity * 0.01
            # In production, use TF to get real distance in every loop
            
        goal_handle.succeed()
        result = SprayAction.Result()
        result.success = True
        result.message = "Target sprayed successfully with latency compensation."
        return result

def main(args=None):
    rclpy.init(args=args)
    node = SprayerActionServer()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()
