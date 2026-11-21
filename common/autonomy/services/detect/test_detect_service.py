"""Unit tests for Nexus object detection service and S1 camera sense."""

import io
from pathlib import Path
import threading
import unittest
from urllib.request import urlopen

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

from detector import ObjectDetector
from service import make_server
from camera_sense import CameraSense
from sense import format_line  # collector: tests never write to the live journal


class TestDetectService(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = make_server("127.0.0.1", 0)
        cls.port = cls.server.server_port
        cls.thread = threading.Thread(target=cls.server.serve_forever)
        cls.thread.daemon = True
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def _make_dummy_jpeg(self) -> bytes:
        if HAS_PIL:
            img = Image.new("RGB", (64, 64), color="red")
            buf = io.BytesIO()
            img.save(buf, format="JPEG")
            return buf.getvalue()
        # Fallback minimal JPEG header
        return b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xdb"

    def test_no_model_never_fabricates_detections(self):
        import io
        from detector import ObjectDetector
        d = ObjectDetector(model_path="", tpu=False)
        self.assertEqual(d.engine, "no_model")
        self.assertFalse(d.model_loaded)
        try:
            from PIL import Image
            buf = io.BytesIO()
            Image.new("RGB", (32, 32), (0, 0, 0)).save(buf, format="JPEG")
            frame = buf.getvalue()
        except ImportError:
            frame = b"\xff\xd8\xff\xe0 not really a jpeg"
        self.assertEqual(d.detect_raw(frame), [])   # a black frame is not a person

    def test_real_model_detection_on_fixtures(self):
        from detector import ObjectDetector
        d = ObjectDetector(tpu=False)
        if not d.model_loaded:
            self.skipTest("ONNX model or onnxruntime not available in environment")
        self.assertEqual(d.engine, "onnx_cpu")
        self.assertTrue(d.model_loaded)

        fixtures_dir = Path(__file__).parent / "fixtures"
        for expected_label, fname in [("cat", "cat.jpg"), ("dog", "dog.jpg"), ("person", "person.jpg")]:
            img_path = fixtures_dir / fname
            self.assertTrue(img_path.is_file(), f"Fixture {img_path} not found")
            detections = d.detect_raw(img_path.read_bytes(), min_confidence=0.4)
            labels = [obj["label"] for obj in detections]
            self.assertIn(expected_label, labels, f"Expected {expected_label} in detected labels {labels}")

    def test_health_check(self):
        url = f"http://127.0.0.1:{self.port}/health"
        with urlopen(url, timeout=2.0) as resp:
            self.assertEqual(resp.status, 200)
            data = resp.read().decode("utf-8")
            self.assertIn("status", data)
            self.assertIn("engine", data)

    def test_no_model_service_yields_no_sense_lines(self):
        url = f"http://127.0.0.1:{self.port}/detect"
        cs = CameraSense(detect_url=url, seen_window_s=60.0, emit_fn=format_line)
        self.assertEqual(cs.process_frame(self._make_dummy_jpeg(), now=100.0), [])

    def test_detect_post_in_memory(self):
        """New-label / repeat logic of the camera sense, with an EXPLICIT test-double detector."""
        from service import DetectRequestHandler

        class TestDoubleDetector(ObjectDetector):
            def detect_raw(self, image_bytes, min_confidence=0.5):
                return [{"label": "person", "confidence": 0.88, "box": [0.1, 0.2, 0.8, 0.7]}]
        real = DetectRequestHandler.detector
        DetectRequestHandler.detector = TestDoubleDetector(tpu=False)
        self.addCleanup(setattr, DetectRequestHandler, "detector", real)
        url = f"http://127.0.0.1:{self.port}/detect"
        jpeg = self._make_dummy_jpeg()
        cs = CameraSense(detect_url=url, seen_window_s=60.0, emit_fn=format_line)

        # First frame with new label should produce P1
        lines = cs.process_frame(jpeg, now=100.0)
        self.assertGreaterEqual(len(lines), 1)
        self.assertIn("NOOBIA P1 camera object.seen", lines[0])

        # Second frame within 60s should produce P0 (not new)
        lines2 = cs.process_frame(jpeg, now=110.0)
        self.assertGreaterEqual(len(lines2), 1)
        self.assertIn("NOOBIA P0 camera object.seen", lines2[0])

        # Third frame after seen_window_s (e.g. 170s) should produce P1 again
        lines3 = cs.process_frame(jpeg, now=175.0)
        self.assertGreaterEqual(len(lines3), 1)
        self.assertIn("NOOBIA P1 camera object.seen", lines3[0])


if __name__ == "__main__":
    unittest.main()
