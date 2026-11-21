"""Detector engine supporting ONNX CPU YOLOv8n and Coral TPU fallback without disk writes."""

from __future__ import annotations

import io
import os
from pathlib import Path
from typing import Any

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    import numpy as np
    import onnxruntime as ort
    HAS_ONNX = True
except ImportError:
    HAS_ONNX = False

NOOBIA_ROOT = Path(os.environ.get("NOOBIA", "/noobia"))
DEFAULT_MODEL_PATH = NOOBIA_ROOT / "common" / "runtime" / "models" / "yolov8n.onnx"

COCO_CLASSES = [
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck", "boat", "traffic light",
    "fire hydrant", "stop sign", "parking meter", "bench", "bird", "cat", "dog", "horse", "sheep", "cow",
    "elephant", "bear", "zebra", "giraffe", "backpack", "umbrella", "handbag", "tie", "suitcase", "frisbee",
    "skis", "snowboard", "sports ball", "kite", "baseball bat", "baseball glove", "skateboard", "surfboard",
    "tennis racket", "bottle", "wine glass", "cup", "fork", "knife", "spoon", "bowl", "banana", "apple",
    "sandwich", "orange", "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair", "couch",
    "potted plant", "bed", "dining table", "toilet", "tv", "laptop", "mouse", "remote", "keyboard", "cell phone",
    "microwave", "oven", "toaster", "sink", "refrigerator", "book", "clock", "vase", "scissors", "teddy bear",
    "hair drier", "toothbrush"
]


def _nms(boxes: list[list[float]], scores: list[float], iou_threshold: float = 0.45) -> list[int]:
    """Non-maximum suppression for normalized bounding boxes."""
    if not boxes:
        return []
    b = np.array(boxes, dtype=np.float32)
    s = np.array(scores, dtype=np.float32)
    x1 = b[:, 0]
    y1 = b[:, 1]
    x2 = b[:, 2]
    y2 = b[:, 3]
    areas = np.maximum(0.0, x2 - x1) * np.maximum(0.0, y2 - y1)
    order = s.argsort()[::-1]

    keep = []
    while order.size > 0:
        i = order[0]
        keep.append(int(i))
        if order.size == 1:
            break
        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])
        w = np.maximum(0.0, xx2 - xx1)
        h = np.maximum(0.0, yy2 - yy1)
        inter = w * h
        union = areas[i] + areas[order[1:]] - inter
        iou = inter / np.maximum(union, 1e-6)
        inds = np.where(iou <= iou_threshold)[0]
        order = order[inds + 1]
    return keep


class ObjectDetector:
    def __init__(self, model_path: str | Path | None = None, tpu: bool = True):
        self.tpu_available = False
        self.engine = "no_model"
        self.model_loaded = False
        self.session = None
        self.input_name = "images"

        # 1. Check for Coral TPU if requested
        if tpu:
            try:
                import pycoral  # noqa: F401
                self.tpu_available = True
                self.engine = "coral_edgetpu"
            except ImportError:
                self.tpu_available = False

        # 2. Check for CPU ONNX model
        resolved_path: Path | None = None
        if model_path is not None:
            if str(model_path).strip():
                resolved_path = Path(model_path)
        else:
            if DEFAULT_MODEL_PATH.is_file():
                resolved_path = DEFAULT_MODEL_PATH

        if resolved_path and resolved_path.is_file() and HAS_ONNX:
            try:
                # Restrict strictly to CPU execution; never load on RTX 5090 next to Qwen
                sess = ort.InferenceSession(str(resolved_path), providers=["CPUExecutionProvider"])
                self.session = sess
                self.input_name = sess.get_inputs()[0].name
                self.model_loaded = True
                self.engine = "onnx_cpu"
            except Exception:
                self.session = None
                self.model_loaded = False
                self.engine = "no_model"

    def detect_raw(self, image_bytes: bytes, min_confidence: float = 0.5) -> list[dict[str, Any]]:
        """Process image bytes purely in memory and return detected objects.

        Invariant: Never persists bytes to filesystem.
        Invariant: Never fabricates a perception without a loaded model.
        """
        if not image_bytes or not self.model_loaded or self.session is None or not HAS_PIL:
            return []

        # Validate image format and decode strictly in memory
        try:
            with Image.open(io.BytesIO(image_bytes)) as img:
                img.verify()
        except Exception:
            return []

        try:
            with Image.open(io.BytesIO(image_bytes)) as img:
                img_rgb = img.convert("RGB")
                orig_w, orig_h = img_rgb.size
                if orig_w <= 0 or orig_h <= 0:
                    return []
                # YOLOv8 expects 640x640 RGB normalized [0..1]
                resized = img_rgb.resize((640, 640))
                arr = np.array(resized, dtype=np.float32) / 255.0
                arr = np.transpose(arr, (2, 0, 1))  # HWC to CHW
                arr = np.expand_dims(arr, axis=0)   # [1, 3, 640, 640]
        except Exception:
            return []

        try:
            outputs = self.session.run(None, {self.input_name: arr})
            out = outputs[0]  # shape [1, 84, N]
            preds = np.squeeze(out).T  # [N, 84]
        except Exception:
            return []

        cand_boxes = []
        cand_scores = []
        cand_classes = []

        for row in preds:
            scores = row[4:]
            cls_id = int(np.argmax(scores))
            conf = float(scores[cls_id])
            if conf >= min_confidence and cls_id < len(COCO_CLASSES):
                cx, cy, w, h = row[:4]
                # Normalize if outputs are in pixel coordinates
                if cx > 1.5 or cy > 1.5 or w > 1.5 or h > 1.5:
                    cx /= 640.0
                    cy /= 640.0
                    w /= 640.0
                    h /= 640.0
                x1 = max(0.0, float(cx - w / 2.0))
                y1 = max(0.0, float(cy - h / 2.0))
                x2 = min(1.0, float(cx + w / 2.0))
                y2 = min(1.0, float(cy + h / 2.0))
                cand_boxes.append([x1, y1, x2, y2])
                cand_scores.append(conf)
                cand_classes.append(cls_id)

        if not cand_boxes:
            return []

        keep_indices = _nms(cand_boxes, cand_scores, iou_threshold=0.45)
        detections: list[dict[str, Any]] = []
        for idx in keep_indices:
            cls_id = cand_classes[idx]
            detections.append({
                "label": COCO_CLASSES[cls_id],
                "confidence": round(cand_scores[idx], 3),
                "box": [round(coord, 3) for coord in cand_boxes[idx]],
            })

        return detections
