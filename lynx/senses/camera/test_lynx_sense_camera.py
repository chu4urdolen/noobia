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


class TestDefaultCaptureSubprocess(unittest.TestCase):
    """The installed H2 tool is a standalone executable; Lynx has no importable
    lynx package, so default_capture must run it via a bounded subprocess and
    fall back to an honest failure when it is missing or misbehaving."""

    JPEG = b"\xff\xd8\xff\xd9"

    def _tool(self, body):
        tool = Path(self._tmp.name) / "lynx-camera-capture"
        tool.write_text("#!/bin/sh\n" + body)
        tool.chmod(0o755)
        return tool

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="lynx-cam-tool-")
        self._orig_env = os.environ.get("NOOBIA_CAMERA_CAPTURE")
        self._orig_import = cam_mod.import_sense
        cam_mod.import_sense = lambda: RecordingSense(sense_mod)

    def tearDown(self):
        cam_mod.import_sense = self._orig_import
        if self._orig_env is None:
            os.environ.pop("NOOBIA_CAMERA_CAPTURE", None)
        else:
            os.environ["NOOBIA_CAMERA_CAPTURE"] = self._orig_env
        self._tmp.cleanup()

    def test_subprocess_capture_success(self):
        tool = self._tool("printf '%s' 'x' # placeholder\n")
        # write raw JPEG bytes with printf escapes
        tool.write_text("#!/bin/sh\nprintf '\\377\\330\\377\\331'\n")
        os.environ["NOOBIA_CAMERA_CAPTURE"] = str(tool)

        ok, frame, msg = cam_mod.default_capture()
        self.assertTrue(ok)
        self.assertEqual(frame, self.JPEG)
        self.assertIn("lynx-camera-capture", msg)

    def test_subprocess_failure_is_honest(self):
        tool = self._tool("echo 'camera stack not loaded' >&2\nexit 1\n")
        os.environ["NOOBIA_CAMERA_CAPTURE"] = str(tool)

        ok, frame, msg = cam_mod.default_capture()
        self.assertFalse(ok)
        self.assertEqual(frame, b"")
        self.assertIn("camera stack not loaded", msg)

    def test_subprocess_timeout_is_bounded(self):
        import subprocess as sp
        from unittest import mock
        tool = self._tool("true\n")
        os.environ["NOOBIA_CAMERA_CAPTURE"] = str(tool)
        with mock.patch("subprocess.run",
                        side_effect=sp.TimeoutExpired("lynx-camera-capture", 8)):
            ok, frame, msg = cam_mod.default_capture()
        self.assertFalse(ok)
        self.assertIn("timed out", msg)

    def test_missing_tool_falls_back_honestly(self):
        os.environ["NOOBIA_CAMERA_CAPTURE"] = str(Path(self._tmp.name) / "absent-tool")

        ok, frame, msg = cam_mod.default_capture()
        self.assertFalse(ok)
        self.assertEqual(frame, b"")
        # repo checkouts reach the importable module (device absent there);
        # Lynx without the tool gets the honest not-installed message.
        self.assertIn("not present", msg)


if __name__ == "__main__":
    unittest.main()
