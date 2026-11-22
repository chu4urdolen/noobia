#!/usr/bin/env python3
"""Unit tests for lynx_sense_motion.py."""

import unittest
import os
from pathlib import Path
import tempfile

os.environ.setdefault("NOOBIA_AUTONOMY_DIR", "/noobia/common/autonomy")

from lynx.senses.motion import lynx_sense_motion as motion


class TestLynxSenseMotion(unittest.TestCase):
    def test_classify_orientation(self):
        self.assertEqual(motion.classify_orientation(50, 100, 9800), "flat_up")
        self.assertEqual(motion.classify_orientation(50, 100, -9800), "flat_down")
        self.assertEqual(motion.classify_orientation(100, 9800, 500), "portrait")
        self.assertEqual(motion.classify_orientation(100, -9800, 500), "inverted")
        self.assertEqual(motion.classify_orientation(9800, 200, 500), "landscape_left")
        self.assertEqual(motion.classify_orientation(-9800, 200, 500), "landscape_right")

    def test_tilt_degrees(self):
        self.assertAlmostEqual(motion.tilt_degrees(0, 0, 9800), 0.0, places=3)
        self.assertAlmostEqual(motion.tilt_degrees(0, 9800, 0), 90.0, places=3)
        self.assertAlmostEqual(motion.tilt_degrees(0, 6930, 6930), 45.0, places=1)
        self.assertAlmostEqual(motion.tilt_degrees(0, 0, -9800), 0.0, places=3)  # face down is flat


class TestPositionDebounce(unittest.TestCase):
    FLAT, UP = [0, 0, 9800], [0, 9800, 300]

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.sf = str(Path(self.tmp.name) / "state.json")
        self._orig_save = motion.save_state
        self.emitted = []

    def tearDown(self):
        self.tmp.cleanup()

    def step(self, raw, now):
        # Not dry: state is saved; emit_line is stubbed so nothing reaches syslog.
        orig = motion.emit_line
        def fake_emit(sense, p, s, event, fields=None, text="", dry_run=False):
            line = f"NOOBIA P{p} {s} {event} " + " ".join(f"{k}={v}" for k, v in (fields or {}).items())
            return line
        motion.emit_line = fake_emit
        try:
            res, code = motion.run(dry_run=False, state_file=self.sf,
                                   reader=lambda: {"raw": raw}, now=now)
        finally:
            motion.emit_line = orig
        self.assertEqual(code, 0)
        lines = [l for l in res["emitted"] if "position.change" in l]
        self.emitted += lines
        return lines

    def test_baseline_says_nothing(self):
        self.assertEqual(self.step(self.FLAT, 1000), [])

    def test_reports_only_after_30s_hold(self):
        self.step(self.FLAT, 1000)
        for t in range(1001, 1030):
            self.assertEqual(self.step(self.UP, t), [], f"too early at t={t}")
        lines = self.step(self.UP, 1031)
        self.assertEqual(len(lines), 1)
        self.assertIn("to=vertical", lines[0])
        self.assertIn("from=horizontal", lines[0])
        # Holding still: no repeats.
        for t in range(1032, 1100):
            self.assertEqual(self.step(self.UP, t), [])

    def test_brief_pickup_is_ignored(self):
        self.step(self.FLAT, 1000)
        for t in range(1001, 1020):
            self.step(self.UP, t)
        for t in range(1020, 1100):
            self.step(self.FLAT, t)
        self.assertEqual(self.emitted, [])

    def test_wobble_resets_the_timer(self):
        self.step(self.FLAT, 1000)
        t = 1001
        for _ in range(5):  # 20 s up, 1 s flat, repeatedly: never 30 s held
            for _ in range(20):
                self.step(self.UP, t); t += 1
            self.step(self.FLAT, t); t += 1
        self.assertEqual(self.emitted, [])

    def test_back_and_forth(self):
        self.step(self.FLAT, 1000)
        for t in range(1001, 1040):
            self.step(self.UP, t)
        for t in range(1040, 1080):
            self.step(self.FLAT, t)
        self.assertEqual(len(self.emitted), 2)
        self.assertIn("to=vertical", self.emitted[0])
        self.assertIn("to=horizontal", self.emitted[1])


if __name__ == "__main__":
    unittest.main()
