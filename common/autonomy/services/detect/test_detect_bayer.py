"""POST /detect_bayer: Lynx's raw CAMSV frames decoded and detected on Nexus."""
from __future__ import annotations

import io
import json
from pathlib import Path
import threading
import unittest
import urllib.error
import urllib.request

try:
    from . import service
except ImportError:
    import service

REAL_FRAME = Path("/noobia/lynx/logs/camera-camsv-frame-1795289981388760796/download_frame.stdout")


class FakeDetector:
    """Different answers per image orientation, so merging can be checked."""
    model_loaded = True
    engine = "fake"
    tpu_available = False

    def __init__(self):
        self.calls = []

    def detect_raw(self, image_bytes, min_confidence=0.5):
        from PIL import Image
        with Image.open(io.BytesIO(image_bytes)) as img:
            w, h = img.size
        self.calls.append((w, h))
        if w > h:   # native (landscape) frame
            return [{"label": "cat", "confidence": 0.61}, {"label": "cell phone", "confidence": 0.55}]
        return [{"label": "cat", "confidence": 0.83}]   # upright variants


class DetectBayerTest(unittest.TestCase):
    def setUp(self):
        self.fake = FakeDetector()
        self._orig_detector = service.DetectRequestHandler.detector
        service.DetectRequestHandler.detector = self.fake
        self._orig_vision = service.VISION_URL
        service.VISION_URL = "http://127.0.0.1:9/none"   # strong models absent in unit tests
        self.server = service.make_server("127.0.0.1", 0)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        service.DetectRequestHandler.detector = self._orig_detector
        service.VISION_URL = self._orig_vision

    def post(self, path, body):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=body, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_merges_variants_by_label_keeping_highest_confidence(self):
        code, body = self.post("/detect_bayer", bytes(range(256)) * 7500)  # 1,920,000 bytes
        self.assertEqual(code, 200, body)
        self.assertEqual(body["objects"][0], {"label": "cat", "confidence": 0.83})
        self.assertIn({"label": "cell_phone", "confidence": 0.55}, body["objects"])
        self.assertEqual(body["variants"], 3)
        self.assertTrue(body["model_loaded"])
        self.assertEqual(sorted(set(self.fake.calls)), [(1200, 1600), (1600, 1200)])

    def test_strong_models_merge_and_caption(self):
        def fake_strong(image, timeout=90.0, yolo_only=False):
            if yolo_only:
                return ({"objects": [{"label": "person", "confidence": 0.81}]}, "ok")
            return ({"objects": [{"label": "cat", "confidence": 0.95, "source": "yolo11x"},
                                 {"label": "keyboard", "confidence": 0.5, "source": "florence2"}],
                     "caption": "A cat lying on a laptop keyboard.", "ms": {"yolo": 900}}, "ok")
        orig = service._strong
        service._strong = fake_strong
        try:
            code, body = self.post("/detect_bayer", bytes(range(256)) * 7500)
        finally:
            service._strong = orig
        self.assertEqual(code, 200)
        self.assertEqual(body["objects"][0], {"label": "cat", "confidence": 0.95})
        self.assertIn({"label": "keyboard", "confidence": 0.5}, body["objects"])
        self.assertEqual(body["caption"], "A cat lying on a laptop keyboard.")
        self.assertIn({"label": "person", "confidence": 0.81}, body["objects"], "zoom crop finds the person")

    def test_strong_models_down_falls_back(self):
        code, body = self.post("/detect_bayer", bytes(range(256)) * 7500)
        self.assertEqual(code, 200)
        self.assertTrue(body["strong_models"].startswith("unavailable"))
        self.assertEqual(body["objects"][0]["label"], "cat")

    def test_wrong_size_is_rejected_with_the_sizes(self):
        code, body = self.post("/detect_bayer", b"\x00" * 1000)
        self.assertEqual(code, 400)
        self.assertIn("1920000", body["error"])
        self.assertIn("1000", body["error"])

    def test_only_known_sensor_sizes(self):
        code, body = self.post("/detect_bayer?w=640&h=480", b"\x00" * (640 * 480))
        self.assertEqual(code, 400)
        self.assertIn("unsupported size", body["error"])
        code, _ = self.post("/detect_bayer?w=3264&h=2448", b"\x10" * (3264 * 2448))
        self.assertEqual(code, 200)

    def test_plain_detect_still_works(self):
        from PIL import Image
        buf = io.BytesIO()
        Image.new("RGB", (64, 48)).save(buf, format="PNG")
        code, body = self.post("/detect", buf.getvalue())
        self.assertEqual(code, 200)
        self.assertIn("objects", body)

    @unittest.skipUnless(REAL_FRAME.is_file(), "real Lynx frame not on this machine")
    def test_real_lynx_frame_decodes_upright(self):
        raw = REAL_FRAME.read_bytes()
        self.assertEqual(len(raw), 1600 * 1200)
        c1 = service._c1()
        from PIL import Image
        png = c1.lift_bayer_to_png(raw)
        with Image.open(io.BytesIO(png)) as img:
            self.assertEqual(img.size, (1600, 1200))
        names = {n: b for n, b in c1.get_detection_frame_variants(png)}
        with Image.open(io.BytesIO(names["upright_wb"])) as img:
            self.assertEqual(img.size, (1200, 1600))
        code, body = self.post("/detect_bayer", raw)
        self.assertEqual(code, 200)
        self.assertEqual(body["objects"][0]["label"], "cat")


if __name__ == "__main__":
    unittest.main()
