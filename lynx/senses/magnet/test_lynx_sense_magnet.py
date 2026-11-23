"""Tests for Lynx magnetometer and compass sense (B3)."""

from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent  # lynx/senses
REPO = HERE.parents[1]
AUTONOMY_DIR = REPO / "common" / "autonomy"

sys.path.insert(0, str(HERE / "common"))
import lynx_senses_lib as lib  # noqa: E402


def _load(name: str, rel: str):
    path = HERE / rel
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


mag = _load("lynx_sense_magnet", "magnet/lynx_sense_magnet.py")


class RecordingSense:
    def __init__(self, real):
        self._real = real
        self.emits = []

    def format_line(self, *a, **k):
        return self._real.format_line(*a, **k)

    def emit(self, *a, **k):
        self.emits.append((a, k))
        return self._real.format_line(*a, **k)


class TestMagnetSense(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.state_file = Path(self._tmp.name) / "state.json"
        spec = importlib.util.spec_from_file_location(
            "noobia_sense_real", AUTONOMY_DIR / "sense.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.recorder = RecordingSense(mod)
        self._orig_import = mag.import_sense
        mag.import_sense = lambda: self.recorder

    def tearDown(self):
        mag.import_sense = self._orig_import
        self._tmp.cleanup()

    def test_first_sample_baselines_quietly(self):
        # Earth ambient field (~45 uT, pointing North)
        res, code = mag.run(
            state_file=str(self.state_file),
            read_mag=lambda: {"raw": [400, 50, -200]},
            now=1000,
        )
        self.assertEqual(code, 0)
        self.assertEqual(res["emitted"], [])
        self.assertEqual(res["state"]["cardinal"], "North")
        self.assertFalse(res["state"].get("wand_active"))

    def test_magnet_wand_detection(self):
        # Ambient sample 1
        mag.run(state_file=str(self.state_file), read_mag=lambda: {"raw": [400, 50, -200]}, now=1000)

        # High flux sample 2 (Magnet brought near: ~300 uT)
        res, code = mag.run(
            state_file=str(self.state_file),
            read_mag=lambda: {"raw": [2500, 1500, 800]},
            now=1002,
        )
        self.assertEqual(code, 0)
        self.assertEqual(len(res["emitted"]), 1)
        line = res["emitted"][0]
        self.assertTrue(line.startswith("NOOBIA P1 magnet wand"))
        self.assertIn("mag_ut=", line)
        self.assertTrue(res["state"]["wand_active"])

    def test_compass_heading_turn(self):
        # Sample 1: facing North (x=400, y=0)
        mag.run(state_file=str(self.state_file), read_mag=lambda: {"raw": [400, 0, -200]}, now=1000)

        # Sample 2: turned to face East (x=0, y=400)
        res, code = mag.run(
            state_file=str(self.state_file),
            read_mag=lambda: {"raw": [0, 400, -200]},
            now=1002,
        )
        self.assertEqual(code, 0)
        self.assertEqual(len(res["emitted"]), 1)
        line = res["emitted"][0]
        self.assertTrue(line.startswith("NOOBIA P1 compass heading"))
        self.assertIn("to=East", line)
        self.assertIn("from=North", line)


if __name__ == "__main__":
    unittest.main()
