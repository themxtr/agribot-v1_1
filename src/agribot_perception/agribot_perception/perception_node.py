from __future__ import annotations

import os
import time

import cv2
import rclpy
import torch
from cv_bridge import CvBridge
from geometry_msgs.msg import Point
from rclpy.lifecycle import Node, State, TransitionCallbackReturn
from sensor_msgs.msg import Image, RegionOfInterest

from agribot_msgs.msg import Detection, DetectionArray

from .sahi_runtime import DetectionRecord, SahiYoloRuntime


class PerceptionNode(Node):
    """Lifecycle ROS2 node running SAHI + YOLOv8 on camera frames."""

    def __init__(self) -> None:
        super().__init__("perception_node")

        self.declare_parameter("model_path", "src/agribot_perception/models/best.onnx")
        self.declare_parameter("device", "cpu")
        self.declare_parameter("conf_threshold", 0.30)
        self.declare_parameter("slice_size", 640)
        self.declare_parameter("overlap_ratio", 0.2)
        self.declare_parameter("nms_iou_threshold", 0.45)
        self.declare_parameter("max_fps", 5.0)
        self.declare_parameter("image_topic", "image_raw")
        self.declare_parameter("annotated_topic", "image_annotated")
        self.declare_parameter("show_window", False)

        self.bridge = CvBridge()
        self.runtime: SahiYoloRuntime | None = None
        self.last_inference_time = 0.0
        self._is_active = False

        self.det_pub = None
        self.annotated_pub = None
        self.subscription = None

    def _resolve_model_path(self) -> str:
        model_path = str(self.get_parameter("model_path").value)
        if os.path.exists(model_path):
            return model_path
        # Support relative path from current working directory.
        maybe = os.path.abspath(model_path)
        if os.path.exists(maybe):
            return maybe
        raise FileNotFoundError(f"Model file not found: {model_path}")

    def _resolve_device(self) -> str:
        requested = str(self.get_parameter("device").value).strip().lower()
        if requested in {"auto", ""}:
            return "cuda:0" if torch.cuda.is_available() else "cpu"
        if requested in {"cuda", "cuda:0", "0"} and not torch.cuda.is_available():
            self.get_logger().warn("CUDA requested but unavailable; falling back to CPU.")
            return "cpu"
        return requested

    def on_configure(self, state: State) -> TransitionCallbackReturn:
        del state
        try:
            model_path = self._resolve_model_path()
            device = self._resolve_device()
            conf_threshold = float(self.get_parameter("conf_threshold").value)
            slice_size = int(self.get_parameter("slice_size").value)
            overlap_ratio = float(self.get_parameter("overlap_ratio").value)
            nms_iou_threshold = float(self.get_parameter("nms_iou_threshold").value)

            self.runtime = SahiYoloRuntime(
                model_path=model_path,
                device=device,
                conf_threshold=conf_threshold,
                slice_size=slice_size,
                overlap_ratio=overlap_ratio,
                nms_iou_threshold=nms_iou_threshold,
            )
            self.get_logger().info(
                "Configured SAHI perception runtime "
                f"(model={model_path}, device={device}, conf={conf_threshold})."
            )
        except Exception as exc:
            self.get_logger().error(f"Failed to configure SAHI runtime: {exc}")
            return TransitionCallbackReturn.FAILURE

        self.det_pub = self.create_lifecycle_publisher(DetectionArray, "detections", 10)
        annotated_topic = str(self.get_parameter("annotated_topic").value)
        self.annotated_pub = self.create_lifecycle_publisher(Image, annotated_topic, 10)

        image_topic = str(self.get_parameter("image_topic").value)
        self.subscription = self.create_subscription(Image, image_topic, self.image_callback, 2)
        return TransitionCallbackReturn.SUCCESS

    def on_activate(self, state: State) -> TransitionCallbackReturn:
        self._is_active = True
        self.get_logger().info("Perception node activated.")
        return super().on_activate(state)

    def on_deactivate(self, state: State) -> TransitionCallbackReturn:
        self._is_active = False
        self.get_logger().info("Perception node deactivated.")
        return super().on_deactivate(state)

    def on_cleanup(self, state: State) -> TransitionCallbackReturn:
        del state
        self.runtime = None
        self.subscription = None
        self._is_active = False
        cv2.destroyAllWindows()
        return TransitionCallbackReturn.SUCCESS

    def _to_detection_array(self, msg: Image, detections: list[DetectionRecord]) -> DetectionArray:
        arr = DetectionArray()
        arr.header = msg.header
        for det in detections:
            x1, y1, x2, y2 = det.bbox_xyxy
            w = max(0, x2 - x1)
            h = max(0, y2 - y1)

            d = Detection()
            d.label = det.class_name
            d.confidence = det.confidence
            d.bbox = RegionOfInterest(
                x_offset=max(0, x1),
                y_offset=max(0, y1),
                width=w,
                height=h,
                do_rectify=False,
            )
            d.stem_pose = Point(
                x=float(x1 + w / 2.0),
                y=float(y1 + h),
                z=0.0,
            )
            arr.detections.append(d)
        return arr

    def image_callback(self, msg: Image) -> None:
        if not self._is_active or self.runtime is None or self.det_pub is None or self.annotated_pub is None:
            return

        max_fps = max(0.1, float(self.get_parameter("max_fps").value))
        now = time.time()
        if (now - self.last_inference_time) < (1.0 / max_fps):
            return

        frame_bgr = self.bridge.imgmsg_to_cv2(msg, desired_encoding="bgr8")
        detections = self.runtime.predict(frame_bgr)
        annotated = self.runtime.annotate(frame_bgr, detections)

        det_array = self._to_detection_array(msg, detections)
        self.det_pub.publish(det_array)

        annotated_msg = self.bridge.cv2_to_imgmsg(annotated, encoding="bgr8")
        annotated_msg.header = msg.header
        self.annotated_pub.publish(annotated_msg)

        if bool(self.get_parameter("show_window").value):
            cv2.imshow("Agribot SAHI Detection", annotated)
            cv2.waitKey(1)

        self.last_inference_time = now


def main(args=None) -> None:
    rclpy.init(args=args)
    node = PerceptionNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
