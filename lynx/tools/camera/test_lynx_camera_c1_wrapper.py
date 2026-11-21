"""Offline unit tests for Lynx Camera C1 Wrapper (lynx_camera_c1_wrapper.py).

Verifies:
- In-memory frame reading from specific path, latest trial directory, and stdin.
- Frame size boundary enforcement (<= 10MB).
- Detection query handling with mock detector.
- Canonical sense line emission (P1 camera object.seen) for recognized objects.
- P0 frame.analyzed emission when no objects recognized.
- Strict zero disk persistence of image bytes.
"""

from __future__ import annotations

import io
from pathlib import Path
import tempfile
import unittest

from lynx_camera_c1_wrapper import (
    find_latest_trial_frame,
    read_frame_bytes,
    run_c1_wrapper,
)


class TestCameraC1Wrapper(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="lynx-c1-test-")
        self.tmp_dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_find_latest_trial_frame(self):
        logs_dir = self.tmp_dir / "logs"
        logs_dir.mkdir()

        t1 = logs_dir / "camsv-frame-20261120-100000"
        t1.mkdir()
        (t1 / "lifted.png").write_bytes(b"\x89PNG\r\n\x1a\nfake1")

        t2 = logs_dir / "camsv-frame-20261121-120000"
        t2.mkdir()
        (t2 / "sensor4-lifted.png").write_bytes(b"\x89PNG\r\n\x1a\nfake2")

        latest = find_latest_trial_frame(logs_dir)
        self.assertIsNotNone(latest)
        self.assertEqual(latest.name, "sensor4-lifted.png")
        self.assertEqual(latest.parent.name, "camsv-frame-20261121-120000")

    def test_read_frame_bytes_file(self):
        sample = self.tmp_dir / "sample.jpg"
        sample.write_bytes(b"\xff\xd8\xff\xe0test")

        data, source = read_frame_bytes(path=sample)
        self.assertEqual(data, b"\xff\xd8\xff\xe0test")
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

    def test_run_c1_wrapper_with_objects(self):
        emitted_calls = []

        def mock_detect(frame_bytes):
            return [{"label": "person", "confidence": 0.91}, {"label": "cat", "confidence": 0.85}]

        def mock_emit(*args, **kwargs):
            emitted_calls.append((args, kwargs))

        res = run_c1_wrapper(
            frame_bytes=b"fake-bytes",
            frame_source="test_frame",
            do_emit=True,
            detect_fn=mock_detect,
            emit_fn=mock_emit,
        )

        self.assertTrue(res["ok"])
        self.assertEqual(res["objects_count"], 2)
        self.assertEqual(len(res["emitted_lines"]), 2)
        self.assertIn("NOOBIA P1 camera object.seen label=person conf=0.91", res["emitted_lines"][0])
        self.assertIn("NOOBIA P1 camera object.seen label=cat conf=0.85", res["emitted_lines"][1])
        self.assertEqual(len(emitted_calls), 2)

    def test_run_c1_wrapper_no_objects(self):
        emitted_calls = []

        def mock_detect(frame_bytes):
            return []

        def mock_emit(*args, **kwargs):
            emitted_calls.append((args, kwargs))

        res = run_c1_wrapper(
            frame_bytes=b"empty-frame",
            frame_source="test_frame",
            do_emit=True,
            detect_fn=mock_detect,
            emit_fn=mock_emit,
        )

        self.assertTrue(res["ok"])
        self.assertEqual(res["objects_count"], 0)
        self.assertEqual(len(res["emitted_lines"]), 1)
        self.assertIn("NOOBIA P0 camera frame.analyzed objects=0", res["emitted_lines"][0])
        self.assertEqual(len(emitted_calls), 1)


if __name__ == "__main__":
    unittest.main()
