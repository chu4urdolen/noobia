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

    def test_health_check(self):
        url = f"http://127.0.0.1:{self.port}/health"
        with urlopen(url, timeout=2.0) as resp:
            self.assertEqual(resp.status, 200)
            data = resp.read().decode("utf-8")
            self.assertIn("status", data)
            self.assertIn("engine", data)

    def test_detect_post_in_memory(self):
        url = f"http://127.0.0.1:{self.port}/detect"
        jpeg = self._make_dummy_jpeg()
        cs = CameraSense(detect_url=url, seen_window_s=60.0)

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
