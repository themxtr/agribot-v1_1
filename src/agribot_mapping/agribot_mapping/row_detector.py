import rclpy
from rclpy.node import Node
from agribot_msgs.msg import DetectionArray
import numpy as np
from sklearn.linear_model import RANSACRegressor
from geometry_msgs.msg import PoseStamped, Point
import tf2_ros

class RowDetector(Node):
    def __init__(self):
        super().__init__('row_detector')
        self.det_sub = self.create_subscription(DetectionArray, 'detections', self.det_cb, 10)
        self.tf_buffer = tf2_ros.Buffer()
        self.tf_listener = tf2_ros.TransformListener(self.tf_buffer, self)
        
        self.get_logger().info('Row Detector initialized.')

    def det_cb(self, msg):
        # Extract 'crop' detections for row fitting
        crops = [d for d in msg.detections if d.label == 'crop']
        
        if len(crops) < 5:
            return

        # Use stem positions for fitting (relative to camera/image)
        # Note: In a real system, these should be projected to ground plane first
        points = np.array([[d.stem_pose.x, d.stem_pose.y] for d in crops])
        
        X = points[:, 1].reshape(-1, 1) # Y is depth-ish in image coords
        y = points[:, 0] # X is lateral
        
        try:
            ransac = RANSACRegressor()
            ransac.fit(X, y)
            
            # Predict row path
            # line_X = np.array([0, 640]).reshape(-1, 1)
            # line_y = ransac.predict(line_X)
            
            self.get_logger().info(f'Detected crop row with {len(ransac.inlier_mask_)} inliers.')
        except Exception as e:
            self.get_logger().error(f'RANSAC failed: {str(e)}')

def main(args=None):
    rclpy.init(args=args)
    node = RowDetector()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()
