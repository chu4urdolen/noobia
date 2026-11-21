"""Detector engine supporting Coral TPU and CPU fallback without disk writes."""

from __future__ import annotations

import io
from typing import Any

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


class ObjectDetector:
    def __init__(self, model_path: str | None = None, tpu: bool = True):
        self.tpu_available = False
        # Honesty rule (Gwyn, 2026-11-21): without a real model this service
        # must never report detections. "no_model" returns nothing.
        self.engine = "no_model"
        self.model_loaded = False

        # Check for Coral TPU / PyCoral if available
        if tpu:
            try:
                import pycoral  # noqa: F401
                self.tpu_available = True
                self.engine = "coral_edgetpu"
            except ImportError:
                self.tpu_available = False
                self.engine = "no_model"

    def detect_raw(self, image_bytes: bytes, min_confidence: float = 0.5) -> list[dict[str, Any]]:
        """Process image bytes purely in memory and return detected objects.

        Invariant: Never persists bytes to filesystem.
        """
        if not image_bytes:
            return []

        # Validate image format in memory
        if HAS_PIL:
            try:
                with Image.open(io.BytesIO(image_bytes)) as img:
                    img.verify()
            except Exception:
                # Invalid image data
                return []

        # If Coral TPU is active and model loaded, invoke inference
        # Otherwise, in CPU fallback mode without model weights, return structured mock/heuristic
        # or parse test tags from frame header if present in testing mode
        # No real inference is implemented yet (no Coral attached, no CPU model).
        # Never fabricate a perception: a Noob must not be told something she
        # did not see. Return nothing until a real model is loaded.
        return []
