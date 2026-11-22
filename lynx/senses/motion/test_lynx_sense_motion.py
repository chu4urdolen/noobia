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

    def test_motion_run_transition_pickup(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = str(Path(tmpdir) / "state.json")

            # First sample: flat_up (baseline, no emission)
            res1, code1 = motion.run(
                dry_run=True,
                state_file=state_file,
                reader=lambda: {"raw": [0, 0, 9800]},
                now=1000,
            )
            self.assertEqual(code1, 0)
            self.assertEqual(res1["emitted"], [])
            self.assertEqual(res1["orientation"], "flat_up")

            # Save state explicitly since dry_run was True
            motion.save_state(Path(state_file), {"samples": 1, "orientation": "flat_up"})

            # Second sample: picked up into portrait -> P1 pickup
            res2, code2 = motion.run(
                dry_run=True,
                state_file=state_file,
                reader=lambda: {"raw": [0, 9800, 200]},
                now=1005,
            )
            self.assertEqual(code2, 0)
            self.assertEqual(len(res2["emitted"]), 1)
            line = res2["emitted"][0]
            self.assertTrue(line.startswith("NOOBIA P1 motion pickup"))
            self.assertIn("to=portrait", line)
            self.assertIn("from=flat_up", line)


if __name__ == "__main__":
    unittest.main()
