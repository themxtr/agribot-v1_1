from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np
from sahi import AutoDetectionModel
from sahi.predict import get_sliced_prediction


@dataclass
class DetectionRecord:
    class_id: int
    class_name: str
    confidence: float
    bbox_xyxy: tuple[int, int, int, int]


class SahiYoloRuntime:
    """SAHI-wrapped YOLO runtime for crop/weed detection and annotation."""

    def __init__(
        self,
        model_path: str,
        device: str,
        conf_threshold: float = 0.25,
        slice_size: int = 640,
        overlap_ratio: float = 0.2,
        nms_iou_threshold: float = 0.75,
    ) -> None:
        self.slice_size = int(slice_size)
        self.overlap_ratio = float(overlap_ratio)
        self.nms_iou_threshold = float(nms_iou_threshold)
        self.conf_threshold = float(conf_threshold)

        self.detector = AutoDetectionModel.from_pretrained(
            model_type="ultralytics",
            model_path=model_path,
            confidence_threshold=self.conf_threshold,
            device=device,
        )

        # OpenCV uses BGR.
        self.class_colors = {
            "crop": (80, 255, 60),      # vivid green
            "weed": (180, 105, 255),    # hot pink-ish
        }

    def _class_color(self, class_name: str) -> tuple[int, int, int]:
        return self.class_colors.get(class_name.lower(), (0, 220, 255))

    def predict(self, frame_bgr: np.ndarray) -> list[DetectionRecord]:
        """Run sliced SAHI inference and return merged detections on full image."""
        prediction = get_sliced_prediction(
            image=frame_bgr,
            detection_model=self.detector,
            slice_height=self.slice_size,
            slice_width=self.slice_size,
            overlap_height_ratio=self.overlap_ratio,
            overlap_width_ratio=self.overlap_ratio,
            postprocess_type="NMS",
            postprocess_match_metric="IOU",
            postprocess_match_threshold=self.nms_iou_threshold,
            verbose=0,
        )

        records: list[DetectionRecord] = []
        for obj in prediction.object_prediction_list:
            x1, y1, x2, y2 = [int(round(v)) for v in obj.bbox.to_xyxy()]
            records.append(
                DetectionRecord(
                    class_id=int(obj.category.id),
                    class_name=str(obj.category.name),
                    confidence=float(obj.score.value),
                    bbox_xyxy=(x1, y1, x2, y2),
                )
            )
        return records

    def annotate(self, frame_bgr: np.ndarray, detections: list[DetectionRecord]) -> np.ndarray:
        """Draw colored class boxes + confidence text onto the frame."""
        out = frame_bgr.copy()
        for det in detections:
            x1, y1, x2, y2 = det.bbox_xyxy
            color = self._class_color(det.class_name)
            cv2.rectangle(out, (x1, y1), (x2, y2), color, 2)
            label = f"{det.class_name} {det.confidence:.2f}"
            cv2.putText(
                out,
                label,
                (x1, max(18, y1 - 8)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                color,
                2,
                cv2.LINE_AA,
            )
        return out
