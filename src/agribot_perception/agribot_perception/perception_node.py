import rclpy
from rclpy.lifecycle import Node, State, TransitionCallbackReturn
from sensor_msgs.msg import Image
from cv_bridge import CvBridge
import cv2
import numpy as np
import onnxruntime as ort
import time
from agribot_msgs.msg import Detection, DetectionArray
from geometry_msgs.msg import Point
from sensor_msgs.msg import RegionOfInterest

class PerceptionNode(Node):
    def __init__(self):
        super().__init__('perception_node')
        self.declare_parameter('model_path', 'yolov8n.onnx')
        self.declare_parameter('conf_threshold', 0.85)
        self.declare_parameter('input_width', 640)
        self.declare_parameter('input_height', 640)
        self.declare_parameter('max_fps', 5.0)
        
        self.bridge = CvBridge()
        self.session = None
        self.last_inference_time = 0
        self.health_pub = self.create_publisher(Point, 'perception_health', 10)
        
    def on_configure(self, state: State) -> TransitionCallbackReturn:
        self.get_logger().info('Configuring Perception Node...')
        
        model_path = self.get_parameter('model_path').value
        self.conf_threshold = self.get_parameter('conf_threshold').value
        self.input_size = (self.get_parameter('input_width').value, 
                           self.get_parameter('input_height').value)
        self.fps_limit = 1.0 / self.get_parameter('max_fps').value

        try:
            # Initialize ONNX Runtime session
            self.session = ort.InferenceSession(model_path, providers=['CPUExecutionProvider'])
            self.get_logger().info(f'Loaded ONNX model from {model_path}')
            
            # Warm-up pass
            dummy_input = np.zeros((1, 3, *self.input_size), dtype=np.float32)
            self.session.run(None, {self.session.get_inputs()[0].name: dummy_input})
            self.get_logger().info('Model warm-up pass successful.')
        except Exception as e:
            self.get_logger().error(f'Failed to load/warm-up ONNX model: {str(e)}')
            return TransitionCallbackReturn.FAILURE

        self.publisher = self.create_lifecycle_publisher(DetectionArray, 'detections', 10)
        self.subscription = self.create_subscription(
            Image, 'image_raw', self.image_callback, 1)
            
        return TransitionCallbackReturn.SUCCESS

    def on_activate(self, state: State) -> TransitionCallbackReturn:
        self.get_logger().info('Activating Perception Node...')
        return super().on_activate(state)

    def on_deactivate(self, state: State) -> TransitionCallbackReturn:
        self.get_logger().info('Deactivating Perception Node...')
        return super().on_deactivate(state)

    def on_cleanup(self, state: State) -> TransitionCallbackReturn:
        self.session = None
        return TransitionCallbackReturn.SUCCESS

    def preprocess(self, img):
        # Resize and normalize
        img_resized = cv2.resize(img, self.input_size)
        img_rgb = cv2.cvtColor(img_resized, cv2.COLOR_BGR2RGB)
        img_float = img_rgb.astype(np.float32) / 255.0
        # HWC to CHW
        img_input = np.transpose(img_float, (2, 0, 1))
        # Add batch dimension
        return np.expand_dims(img_input, axis=0)

    def image_callback(self, msg):
        if self.session is None or self.active_state.id != State.PRIMARY_STATE_ACTIVE:
            return

        # Simple FPS control
        current_time = time.time()
        if (current_time - self.last_inference_time) < self.fps_limit:
            return

        cv_image = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
        orig_h, orig_w = cv_image.shape[:2]

        # Standard YOLOv8 ONNX inference
        blob = self.preprocess(cv_image)
        outputs = self.session.run(None, {self.session.get_inputs()[0].name: blob})
        
        # Post-process (Assumes YOLOv8 output: [batch, 4+num_classes, num_anchors])
        # This part should be adapted to the specific model output format
        detections = outputs[0][0]
        detections = np.transpose(detections) # [num_anchors, 4 + num_classes]
        
        det_array = DetectionArray()
        det_array.header = msg.header
        
        for row in detections:
            classes_scores = row[4:]
            class_id = np.argmax(classes_scores)
            score = classes_scores[class_id]
            
            if score > self.conf_threshold:
                # YOLOv8 outputs cx, cy, w, h
                cx, cy, w, h = row[:4]
                
                # Scale back to original image size
                # Note: YOLOv8 outputs are often already scaled to input size (e.g. 640)
                # Here we assume they need scaling relative to 640
                scale_x = orig_w / self.input_size[0]
                scale_y = orig_h / self.input_size[1]
                
                left = (cx - w/2) * scale_x
                top = (cy - h/2) * scale_y
                width = w * scale_x
                height = h * scale_y

                det = Detection()
                det.label = 'crop' if class_id == 0 else 'weed'
                det.confidence = float(score)
                det.bbox = RegionOfInterest(
                    x_offset=int(max(0, left)),
                    y_offset=int(max(0, top)),
                    width=int(width),
                    height=int(height),
                    do_rectify=False
                )
                
                # Heuristic Stem Position: Bottom middle of bounding box
                det.stem_pose = Point(
                    x=float(left + width/2),
                    y=float(top + height),
                    z=0.0
                )
                
                det_array.detections.append(det)

        self.publisher.publish(det_array)
        self.last_inference_time = current_time

def main(args=None):
    rclpy.init(args=args)
    node = PerceptionNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()
