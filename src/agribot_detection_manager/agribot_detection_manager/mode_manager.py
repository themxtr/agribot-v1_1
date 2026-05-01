import rclpy
from rclpy.lifecycle import Node, State, TransitionCallbackReturn
from std_msgs.msg import String
from agribot_msgs.msg import DetectionArray
from lifecycle_msgs.srv import ChangeState
from lifecycle_msgs.msg import Transition
import time

class ModeManager(Node):
    def __init__(self):
        super().__init__('mode_manager')
        self.declare_parameter('start_mode', 'SCAN')
        self.current_mode = self.get_parameter('start_mode').value
        
        # Clients for other lifecycle nodes
        self.perception_client = self.create_client(ChangeState, '/perception_node/change_state')
        
        self.mode_sub = self.create_subscription(String, 'set_mode', self.mode_cb, 10)
        self.det_sub = self.create_subscription(DetectionArray, 'detections', self.det_cb, 10)
        
        self.get_logger().info(f'Mode Manager initialized. Initial mode: {self.current_mode}')

    def on_configure(self, state: State) -> TransitionCallbackReturn:
        self.get_logger().info('Configuring Mode Manager...')
        return TransitionCallbackReturn.SUCCESS

    def on_activate(self, state: State) -> TransitionCallbackReturn:
        self.get_logger().info('Activating Mode Manager...')
        # Initial transition for perception node
        self.transition_node(self.perception_client, Transition.TRANSITION_CONFIGURE)
        self.transition_node(self.perception_client, Transition.TRANSITION_ACTIVATE)
        return TransitionCallbackReturn.SUCCESS

    def mode_cb(self, msg):
        new_mode = msg.data.upper()
        if new_mode in ['SCAN', 'DETECT', 'SPRAY']:
            self.get_logger().info(f'Switching to mode: {new_mode}')
            self.current_mode = new_mode
            # Handle node reconfiguration based on mode
            self.handle_mode_transition(new_mode)

    def handle_mode_transition(self, mode):
        # Example: In SPRAY mode, we might want higher confidence or lower FPS to save power
        # Or trigger specific tracking behaviors
        pass

    def transition_node(self, client, transition_id):
        if not client.wait_for_service(timeout_sec=1.0):
            self.get_logger().warn(f'Service {client.srv_name} not available')
            return
        
        req = ChangeState.Request()
        req.transition.id = transition_id
        client.call_async(req)

    def det_cb(self, msg):
        # Filtering and tracking based on current mode
        if self.current_mode == 'SCAN':
            # Low throughput mapping logic
            pass
        elif self.current_mode == 'DETECT':
            # High precision tracking logic
            pass
        elif self.current_mode == 'SPRAY':
            # Visual servoing / alignment validation
            pass

def main(args=None):
    rclpy.init(args=args)
    node = ModeManager()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()
