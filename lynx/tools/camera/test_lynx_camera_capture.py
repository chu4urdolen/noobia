"""Unit tests for lynx-camera-capture tool (H2 / S1)."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from lynx_camera_capture import (
    capture_one_frame,
    is_disabled,
    MINIMAL_JPEG_BYTES,
)


class TestCameraCapture(unittest.TestCase):
    def test_dry_run_returns_valid_jpeg(self):
        ok, img_bytes, msg = capture_one_frame(dry_run=True)
        self.assertTrue(ok)
        self.assertTrue(img_bytes.startswith(b"\xff\xd8"))
        self.assertTrue(img_bytes.endswith(b"\xff\xd9"))
        self.assertIn("synthetic JPEG", msg)

    def test_disable_switch_inhibits_capture(self):
        with tempfile.NamedTemporaryFile("w", delete=False) as tf:
            switch_path = tf.name

        try:
            self.assertTrue(is_disabled(switch_path))
            ok, img_bytes, msg = capture_one_frame(disable_switch=switch_path)
            self.assertFalse(ok)
            self.assertEqual(img_bytes, b"")
            self.assertIn("disable switch", msg)
        finally:
            Path(switch_path).unlink(missing_ok=True)

    def test_missing_device_fails_honestly(self):
        ok, img_bytes, msg = capture_one_frame(device="/dev/video_nonexistent_999", dry_run=False)
        self.assertFalse(ok)
        self.assertEqual(img_bytes, b"")
        self.assertIn("not present", msg)

    def test_cli_dry_run_json_output(self):
        cmd = [sys.executable, str(Path(__file__).parent / "lynx_camera_capture.py"), "--dry-run", "--json"]
        res = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0)
        data = json.loads(res.stdout)
        self.assertTrue(data.get("ok"))
        self.assertGreater(data.get("bytes", 0), 0)

    def test_cli_output_file_writing(self):
        with tempfile.NamedTemporaryFile("wb", delete=False) as tf:
            out_path = Path(tf.name)

        try:
            cmd = [
                sys.executable,
                str(Path(__file__).parent / "lynx_camera_capture.py"),
                "--dry-run",
                "--output",
                str(out_path),
            ]
            res = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(res.returncode, 0)
            self.assertTrue(out_path.exists())
            self.assertEqual(out_path.read_bytes(), MINIMAL_JPEG_BYTES)
        finally:
            out_path.unlink(missing_ok=True)

    def test_cli_disable_switch_exit_two(self):
        with tempfile.NamedTemporaryFile("w", delete=False) as tf:
            switch_path = tf.name

        try:
            cmd = [
                sys.executable,
                str(Path(__file__).parent / "lynx_camera_capture.py"),
                "--disable-switch",
                switch_path,
                "--json",
            ]
            res = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(res.returncode, 2)
            data = json.loads(res.stdout)
            self.assertFalse(data.get("ok"))
            self.assertIn("disable switch", data.get("error", ""))
        finally:
            Path(switch_path).unlink(missing_ok=True)

    def test_non_jpeg_frame_fails_loudly_never_a_placeholder(self):
        """Raw Bayer bytes must be an honest failure, not a fake 'empty' image."""
        with tempfile.TemporaryDirectory() as d:
            dev = Path(d) / "video145"
            dev.write_bytes(b"\x10\x20" * 5000)   # Bayer-like, not JPEG
            ok, frame, msg = capture_one_frame(device=str(dev), timeout_s=1.0,
                                               disable_switch=Path(d) / "off")
            self.assertFalse(ok)
            self.assertEqual(frame, b"")
            self.assertIn("not a JPEG", msg)
            dev.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 64)   # a real JPEG start
            ok, frame, msg = capture_one_frame(device=str(dev), timeout_s=1.0,
                                               disable_switch=Path(d) / "off")
            self.assertTrue(ok)
            self.assertTrue(frame.startswith(b"\xff\xd8"))


if __name__ == "__main__":
    unittest.main()
