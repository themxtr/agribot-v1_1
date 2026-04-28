import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from cv_bridge import CvBridge
import cv2
from agribot_msgs.msg import Detection, DetectionArray
# Assuming ultralytics is installed for YOLOv8
try:
    from ultralytics import YOLO
except ImportError:
    YOLO = None

class DetectionNode(Node):
    def __init__(self):
        super().__init__('detection_node')
        self.declare_parameter('model_path', 'yolov8n.pt')
        self.declare_parameter('confidence_threshold', 0.5)
        
        model_path = self.get_parameter('model_path').get_parameter_value().string_value
        self.conf_threshold = self.get_parameter('confidence_threshold').get_parameter_value().double_value
        
        if YOLO:
            import torch
            self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
            self.get_logger().info(f'CUDA available: {torch.cuda.is_available()}, forcing device: {self.device}')
            self.model = YOLO(model_path)
            self.get_logger().info(f'Loaded YOLOv8 model from {model_path}')
        else:
            self.get_logger().error('ultralytics package not found. Please install with: pip install ultralytics')
            self.model = None

        self.subscription = self.create_subscription(
            Image,
            'image_raw',
            self.image_callback,
            10)
        self.publisher = self.create_publisher(DetectionArray, 'detections', 10)
        self.bridge = CvBridge()

    def image_callback(self, msg):
        if self.model is None:
            return

        cv_image = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
        
        # Run inference
        results = self.model(cv_image, conf=self.conf_threshold, device=self.device)
        
        detection_array = DetectionArray()
        
        for result in results:
            for box in result.boxes:
                detection = Detection()
                
                # Get label name
                class_id = int(box.cls[0])
                label = self.model.names[class_id]
                
                # Filter for crops and weeds (assuming model has these classes)
                # For demo purposes, we'll just check if 'weed' or 'crop' is in label
                detection.label = label
                
                # Normalize coordinates (or use pixel coordinates depending on control logic)
                # Here we use center coordinates
                x_center = float((box.xyxy[0][0] + box.xyxy[0][2]) / 2)
                y_center = float((box.xyxy[0][1] + box.xyxy[0][3]) / 2)
                
                from sensor_msgs.msg import RegionOfInterest
                from geometry_msgs.msg import Point
                detection.bbox = RegionOfInterest(
                    x_offset=int(box.xyxy[0][0]),
                    y_offset=int(box.xyxy[0][1]),
                    width=int(box.xyxy[0][2] - box.xyxy[0][0]),
                    height=int(box.xyxy[0][3] - box.xyxy[0][1]),
                    do_rectify=False
                )
                detection.stem_pose = Point(
                    x=x_center,
                    y=y_center,
                    z=0.0
                )
                detection.confidence = float(box.conf[0])
                
                detection_array.detections.append(detection)
        
        self.publisher.publish(detection_array)
        # self.get_logger().info(f'Published {len(detection_array.detections)} detections')

def main(args=None):
    rclpy.init(args=args)
    node = DetectionNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()
