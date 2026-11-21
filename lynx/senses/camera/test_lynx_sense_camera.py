"""Offline unit tests for Lynx S1 camera sense (lynx_sense_camera.py).

Verifies:
- Hardware disable switch inhibition.
- Capture unavailability handling (honest reporting, no loop failure).
- Detection service error handling.
- P1 emission on new object labels.
- P0 emission on repeated object labels within window (300s).
- P1 emission after window expiration (hysteresis).
- State persistence and dry-run isolation.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
SENSES_DIR = HERE.parent
AUTONOMY_DIR = HERE.parents[2] / "common" / "autonomy"

# Load sense.py
spec = importlib.util.spec_from_file_location("sense", AUTONOMY_DIR / "sense.py")
sense_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sense_mod)

# Load camera sense
import sys
sys.path.insert(0, str(SENSES_DIR / "common"))
spec_cam = importlib.util.spec_from_file_location("lynx_sense_camera", HERE / "lynx_sense_camera.py")
cam_mod = importlib.util.module_from_spec(spec_cam)
spec_cam.loader.exec_module(cam_mod)


class RecordingSense:
    def __init__(self, real):
        self._real = real
        self.emits = []

    def format_line(self, *a, **k):
        return self._real.format_line(*a, **k)

    def emit(self, *a, **k):
        self.emits.append((a, k))
        return self._real.format_line(*a, **k)


class TestCameraSense(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="lynx-cam-test-")
        self.state_file = Path(self._tmp.name) / "state.json"
        self.recorder = RecordingSense(sense_mod)
        self._orig_import = cam_mod.import_sense
        cam_mod.import_sense = lambda: self.recorder

    def tearDown(self):
        cam_mod.import_sense = self._orig_import
        self._tmp.cleanup()

    def test_camera_disabled(self):
        switch = Path(self._tmp.name) / "disable-switch"
        switch.touch()
        orig_check = cam_mod.is_camera_disabled
        cam_mod.is_camera_disabled = lambda: True
        try:
            res, code = cam_mod.run(state_file=str(self.state_file))
            self.assertEqual(code, 0)
            self.assertTrue(res.get("disabled"))
            self.assertEqual(len(res.get("emitted", [])), 0)
        finally:
            cam_mod.is_camera_disabled = orig_check

    def test_capture_unavailable(self):
        def mock_capture():
            return False, b"", "device /dev/video145 not present"

        res, code = cam_mod.run(state_file=str(self.state_file), capture_fn=mock_capture)
        self.assertEqual(code, 0)
        self.assertFalse(res.get("available"))
        self.assertEqual(len(res.get("emitted", [])), 0)

    def test_detect_failure(self):
        def mock_capture():
            return True, b"\xff\xd8\xff\xd9", "captured"

        def mock_detect(frame):
            raise ConnectionError("Nexus detect port unreachable")

        res, code = cam_mod.run(
            state_file=str(self.state_file),
            capture_fn=mock_capture,
            detect_fn=mock_detect,
        )
        self.assertEqual(code, 1)
        self.assertFalse(res.get("ok"))
        self.assertIn("ConnectionError", res.get("error", ""))

    def test_detect_new_and_repeated_labels(self):
        def mock_capture():
            return True, b"\xff\xd8\xff\xd9", "captured"

        def mock_detect(frame):
            return [{"label": "person", "confidence": 0.88}]

        # Step 1: First sighting at t=1000 -> expect P1
        res1, code1 = cam_mod.run(
            state_file=str(self.state_file),
            capture_fn=mock_capture,
            detect_fn=mock_detect,
            now=1000.0,
        )
        self.assertEqual(code1, 0)
        self.assertEqual(len(res1["emitted"]), 1)
        self.assertIn("NOOBIA P1 camera object.seen", res1["emitted"][0])
        self.assertIn("label=person", res1["emitted"][0])
        self.assertIn("conf=0.88", res1["emitted"][0])

        # Step 2: Repeated sighting at t=1050 (50s later < 300s window) -> expect P0
        res2, code2 = cam_mod.run(
            state_file=str(self.state_file),
            capture_fn=mock_capture,
            detect_fn=mock_detect,
            now=1050.0,
        )
        self.assertEqual(code2, 0)
        self.assertEqual(len(res2["emitted"]), 1)
        self.assertIn("NOOBIA P0 camera object.seen", res2["emitted"][0])

        # Step 3: Sighting at t=1400 (350s later >= 300s window) -> expect P1 again
        res3, code3 = cam_mod.run(
            state_file=str(self.state_file),
            capture_fn=mock_capture,
            detect_fn=mock_detect,
            now=1400.0,
        )
        self.assertEqual(code3, 0)
        self.assertEqual(len(res3["emitted"]), 1)
        self.assertIn("NOOBIA P1 camera object.seen", res3["emitted"][0])

    def test_dry_run_does_not_save_state(self):
        def mock_capture():
            return True, b"\xff\xd8\xff\xd9", "captured"

        def mock_detect(frame):
            return [{"label": "cat", "confidence": 0.95}]

        res, code = cam_mod.run(
            dry_run=True,
            state_file=str(self.state_file),
            capture_fn=mock_capture,
            detect_fn=mock_detect,
            now=2000.0,
        )
        self.assertEqual(code, 0)
        self.assertEqual(len(res["emitted"]), 1)
        self.assertFalse(self.state_file.exists())
        self.assertEqual(len(self.recorder.emits), 0)  # Dry run doesn't emit to syslog


if __name__ == "__main__":
    unittest.main()
