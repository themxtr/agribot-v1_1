from __future__ import annotations
import cv2
import numpy as np
import torch
import torchvision
from dataclasses import dataclass
from typing import Any
from sahi import AutoDetectionModel
from sahi.predict import get_sliced_prediction

@dataclass
class DetectionRecord:
    class_id: int
    class_name: str
    confidence: float
    bbox_xyxy: tuple[int, int, int, int]

class SahiYoloRuntime:
    """SAHI-wrapped YOLO runtime with Cross-Class NMS dual-label suppression."""

    def __init__(
        self,
        model_path: str,
        device: str = 'cpu',
        conf_threshold: float = 0.30,
        slice_size: int = 640,
        overlap_ratio: float = 0.2,
        nms_iou_threshold: float = 0.45,  # Suppress cross-class overlap > 0.45
    ) -> None:
        self.slice_size = int(slice_size)
        self.overlap_ratio = float(overlap_ratio)
        self.nms_iou_threshold = float(nms_iou_threshold)
        self.conf_threshold = float(conf_threshold)
        self.device = device

        self.detector = AutoDetectionModel.from_pretrained(
            model_type="ultralytics",
            model_path=model_path,
            confidence_threshold=self.conf_threshold,
            device=self.device,
        )

        # Rendering colors
        self.class_colors = {
            0: (0, 255, 0),      # Vivid Green (Crop)
            1: (203, 105, 255),  # Hot Pink (Weed) - BGR: 255, 105, 180 (approx)
        }
        self.class_names = {0: "crop", 1: "weed"}

    def _apply_cross_class_nms(self, records: list[DetectionRecord]) -> list[DetectionRecord]:
        """
        Suppresses lower-confidence boxes of DIFFERENT classes 
        if they overlap > self.nms_iou_threshold.
        """
        if not records:
            return []

        boxes = torch.tensor([r.bbox_xyxy for r in records], dtype=torch.float32)
        scores = torch.tensor([r.confidence for r in records], dtype=torch.float32)
        
        # In torchvision.ops.nms, if we don't provide class IDs, it performs cross-class NMS
        keep_indices = torchvision.ops.nms(boxes, scores, self.nms_iou_threshold)
        
        return [records[i] for i in keep_indices]

    def predict(self, frame_bgr: np.ndarray) -> list[DetectionRecord]:
        """Run sliced SAHI inference and apply cross-class NMS."""
        prediction = get_sliced_prediction(
            image=frame_bgr,
            detection_model=self.detector,
            slice_height=self.slice_size,
            slice_width=self.slice_size,
            overlap_height_ratio=self.overlap_ratio,
            overlap_width_ratio=self.overlap_ratio,
            postprocess_type="NMS",
            postprocess_match_metric="IOU",
            postprocess_match_threshold=0.75, # SAHI internal per-class merge
            verbose=0,
        )

        raw_records: list[DetectionRecord] = []
        for obj in prediction.object_prediction_list:
            x1, y1, x2, y2 = [int(round(v)) for v in obj.bbox.to_xyxy()]
            raw_records.append(
                DetectionRecord(
                    class_id=int(obj.category.id),
                    class_name=str(obj.category.name),
                    confidence=float(obj.score.value),
                    bbox_xyxy=(x1, y1, x2, y2),
                )
            )
            
        # Apply Cross-Class NMS dual-label suppression
        return self._apply_cross_class_nms(raw_records)

    def annotate(self, frame_bgr: np.ndarray, detections: list[DetectionRecord]) -> np.ndarray:
        """Draw colored class boxes + confidence text onto the frame."""
        out = frame_bgr.copy()
        for det in detections:
            x1, y1, x2, y2 = det.bbox_xyxy
            color = self.class_colors.get(det.class_id, (255, 255, 255))
            
            # Vivid labeling
            cv2.rectangle(out, (x1, y1), (x2, y2), color, 3)
            label = f"{det.class_name.upper()} {det.confidence:.2f}"
            
            # Text background for readability
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
            cv2.rectangle(out, (x1, y1 - th - 10), (x1 + tw, y1), color, -1)
            cv2.putText(
                out,
                label,
                (x1, y1 - 8),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (255, 255, 255), # White text
                2,
                cv2.LINE_AA,
            )
        return out
