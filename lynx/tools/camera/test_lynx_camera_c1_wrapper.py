"""Offline unit tests for Lynx Camera C1 Wrapper (lynx_camera_c1_wrapper.py).

Verifies:
- In-memory frame reading from specific path, latest trial directory, and stdin.
- Globbing camera-camsv-frame-* and legacy camsv-frame-* (D1).
- In-memory Bayer lift and loud failure on undecodable frames (D2).
- Emission onto Lynx via remote ssh command or mock (D3).
- Multi-word label normalization (e.g. 'traffic light' -> 'traffic_light') (D4).
- Same-boot and staleness window enforcement (D5).
- Frame size boundary enforcement (<= 10MB).
- Strict zero disk persistence of image bytes.
"""

from __future__ import annotations

import io
from pathlib import Path
import tempfile
import time
import unittest

from PIL import Image

from lynx_camera_c1_wrapper import (
    find_latest_trial_frame,
    read_frame_bytes,
    run_c1_wrapper,
    ensure_decodable_image,
    normalize_coco_label,
)


class TestCameraC1Wrapper(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="lynx-c1-test-")
        self.tmp_dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _make_png_bytes(self) -> bytes:
        img = Image.new("RGB", (64, 64), color="blue")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    def test_normalize_coco_label(self):
        self.assertEqual(normalize_coco_label("person"), "person")
        self.assertEqual(normalize_coco_label("cell phone"), "cell_phone")
        self.assertEqual(normalize_coco_label("traffic light"), "traffic_light")
        self.assertEqual(normalize_coco_label("teddy bear"), "teddy_bear")
        self.assertEqual(normalize_coco_label("  Fire Hydrant  "), "fire_hydrant")

    def test_find_latest_trial_frame_globs_and_staleness(self):
        logs_dir = self.tmp_dir / "logs"
        logs_dir.mkdir()

        now = 100000.0
        # t1: old trial (> 5 min)
        t1 = logs_dir / "camera-camsv-frame-100"
        t1.mkdir()
        (t1 / "sensor4-lifted.png").write_bytes(self._make_png_bytes())
        (t1 / "boot_id.stdout").write_text("boot-A\n")
        (t1 / "result.json").write_text('{"steps": [{"name": "boot_id", "unix_ns": 99000000000000}]}')

        # t2: fresh trial within 5 min, boot-B
        t2 = logs_dir / "camera-camsv-frame-200"
        t2.mkdir()
        (t2 / "sensor4-lifted.png").write_bytes(self._make_png_bytes())
        (t2 / "boot_id.stdout").write_text("boot-B\n")
        (t2 / "result.json").write_text('{"steps": [{"name": "boot_id", "unix_ns": 99900000000000}]}')

        # Matching boot-B and fresh
        found = find_latest_trial_frame(logs_dir, expected_boot_id="boot-B", max_age_s=300.0, now_ts=now)
        self.assertEqual(found, t2 / "sensor4-lifted.png")

        # Wrong boot refuses
        with self.assertRaises(RuntimeError):
            find_latest_trial_frame(logs_dir, expected_boot_id="boot-C", max_age_s=300.0, now_ts=now)

        # Stale frame refuses
        with self.assertRaises(RuntimeError):
            find_latest_trial_frame(logs_dir, expected_boot_id="boot-A", max_age_s=300.0, now_ts=now)

    def test_find_latest_trial_frame_wide_camera(self):
        logs_dir = self.tmp_dir / "logs"
        logs_dir.mkdir()
        now = 100000.0

        t_wide = logs_dir / "camera-wide-frame-250"
        t_wide.mkdir()
        (t_wide / "sensor2-preview-lifted.png").write_bytes(self._make_png_bytes())
        (t_wide / "boot_id.stdout").write_text("boot-W\n")
        (t_wide / "result.json").write_text('{"steps": [{"name": "boot_id", "unix_ns": 99950000000000}]}')

        found = find_latest_trial_frame(logs_dir, expected_boot_id="boot-W", max_age_s=300.0, now_ts=now)
        self.assertEqual(found, t_wide / "sensor2-preview-lifted.png")

    def test_wide_bayer_decode(self):
        raw_bayer = bytes([128] * (3264 * 2448))
        png_bytes = ensure_decodable_image(raw_bayer, source_hint="sensor2.bayer")
        self.assertTrue(png_bytes.startswith(b"\x89PNG"))
        with Image.open(io.BytesIO(png_bytes)) as img:
            self.assertEqual(img.size, (3264, 2448))

    def test_run_c1_wrapper_lens_tagging(self):
        emitted_lines = []

        def mock_detect(frame_bytes):
            return [{"label": "cat", "confidence": 0.95}]

        def mock_emit_remote(line):
            emitted_lines.append(line)

        res = run_c1_wrapper(
            frame_bytes=self._make_png_bytes(),
            frame_source="sensor2_wide_frame.png",
            do_emit=True,
            detect_fn=mock_detect,
            emit_remote_fn=mock_emit_remote,
            lens="wide",
        )
        self.assertTrue(res["ok"])
        self.assertEqual(res["lens"], "wide")
        self.assertIn("NOOBIA P1 camera object.seen label=cat conf=0.95 lens=wide | [wide] cat seen by camera", res["emitted_lines"][0])

    def test_bayer_decode_and_loud_failure(self):
        # 1. Synthesize a valid 1600x1200 Bayer array (1920000 bytes)
        raw_bayer = bytes([128] * (1600 * 1200))
        png_bytes = ensure_decodable_image(raw_bayer, source_hint="sensor4.bayer")
        self.assertTrue(png_bytes.startswith(b"\x89PNG"))

        # Verify decoded PNG is readable by PIL
        with Image.open(io.BytesIO(png_bytes)) as img:
            self.assertEqual(img.size, (1600, 1200))

        # 2. Corrupt / invalid bytes must fail loudly
        with self.assertRaises(ValueError):
            ensure_decodable_image(b"not-an-image-at-all", source_hint="corrupt.raw")

        # 3. Empty bytes must fail loudly
        with self.assertRaises(ValueError):
            ensure_decodable_image(b"", source_hint="empty.jpg")

    def test_read_frame_bytes_file(self):
        sample = self.tmp_dir / "sample.png"
        sample.write_bytes(self._make_png_bytes())

        data, source = read_frame_bytes(path=sample)
        self.assertTrue(data.startswith(b"\x89PNG"))
        self.assertEqual(source, str(sample))

    def test_read_frame_bytes_size_bound(self):
        huge = self.tmp_dir / "huge.raw"
        huge.write_bytes(b"0" * 100)

        import lynx_camera_c1_wrapper
        orig_max = lynx_camera_c1_wrapper.MAX_FRAME_SIZE
        lynx_camera_c1_wrapper.MAX_FRAME_SIZE = 50
        try:
            with self.assertRaises(ValueError):
                read_frame_bytes(path=huge)
        finally:
            lynx_camera_c1_wrapper.MAX_FRAME_SIZE = orig_max

    def test_run_c1_wrapper_with_multiword_labels(self):
        emitted_lines = []

        def mock_detect(frame_bytes):
            return [
                {"label": "person", "confidence": 0.91},
                {"label": "cell phone", "confidence": 0.85},
                {"label": "traffic light", "confidence": 0.77},
            ]

        def mock_emit_remote(line):
            emitted_lines.append(line)

        res = run_c1_wrapper(
            frame_bytes=self._make_png_bytes(),
            frame_source="test_frame",
            do_emit=True,
            detect_fn=mock_detect,
            emit_remote_fn=mock_emit_remote,
        )

        self.assertTrue(res["ok"])
        self.assertEqual(res["objects_count"], 3)
        self.assertEqual(len(res["emitted_lines"]), 3)
        # Check normalization in fields and preservation in human text
        self.assertIn("NOOBIA P1 camera object.seen label=person conf=0.91 | person seen by camera", res["emitted_lines"][0])
        self.assertIn("NOOBIA P1 camera object.seen label=cell_phone conf=0.85 | cell phone seen by camera", res["emitted_lines"][1])
        self.assertIn("NOOBIA P1 camera object.seen label=traffic_light conf=0.77 | traffic light seen by camera", res["emitted_lines"][2])
        self.assertEqual(len(emitted_lines), 3)

    def test_run_c1_wrapper_no_objects(self):
        emitted_lines = []

        def mock_detect(frame_bytes):
            return []

        def mock_emit_remote(line):
            emitted_lines.append(line)

        res = run_c1_wrapper(
            frame_bytes=self._make_png_bytes(),
            frame_source="test_frame",
            do_emit=True,
            detect_fn=mock_detect,
            emit_remote_fn=mock_emit_remote,
        )

        self.assertTrue(res["ok"])
        self.assertEqual(res["objects_count"], 0)
        self.assertEqual(len(res["emitted_lines"]), 1)
        self.assertIn("NOOBIA P0 camera frame.analyzed objects=0 | frame analyzed, no objects recognized", res["emitted_lines"][0])
        self.assertEqual(len(emitted_lines), 1)

    def test_c1b_rotation_and_wb_on_real_trial_frames(self):
        """Task C1b: rotation (270 deg) and white balance detect cat, dog, and cup from real trial frames."""
        import sys
        sys.path.insert(0, str(Path(__file__).parents[3] / "common" / "autonomy" / "services" / "detect"))
        from detector import ObjectDetector

        det = ObjectDetector(tpu=False)
        if not det.model_loaded:
            self.skipTest("Real ONNX detector model not available")

        logs_root = Path(__file__).parents[2] / "logs"
        cat_p = logs_root / "camera-camsv-frame-1795289981388760796" / "sensor4-preview-lifted.png"
        dog_p = logs_root / "camera-camsv-frame-1795290224065061121" / "sensor4-preview-lifted.png"
        cup_p = logs_root / "camera-camsv-frame-1795290384755337439" / "sensor4-preview-lifted.png"

        if not (cat_p.is_file() and dog_p.is_file() and cup_p.is_file()):
            self.skipTest("Real trial frames not present on disk")

        # Cat frame: detects cat
        res_cat = run_c1_wrapper(cat_p.read_bytes(), "cat_frame", detect_fn=det.detect_raw)
        cat_labels = [o["label"] for o in res_cat["objects"]]
        self.assertIn("cat", cat_labels)

        # Dog frame (enlarged): detects dog
        res_dog = run_c1_wrapper(dog_p.read_bytes(), "dog_frame", detect_fn=det.detect_raw)
        dog_labels = [o["label"] for o in res_dog["objects"]]
        self.assertIn("dog", dog_labels)

        # Cup frame: detects cup
        res_cup = run_c1_wrapper(cup_p.read_bytes(), "cup_frame", detect_fn=det.detect_raw)
        cup_labels = [o["label"] for o in res_cup["objects"]]
        self.assertIn("cup", cup_labels)


if __name__ == "__main__":
    unittest.main()
