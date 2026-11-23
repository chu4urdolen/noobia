"""Tests for Lynx alert slider sense (B1)."""

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


slider = _load("lynx_sense_slider", "slider/lynx_sense_slider.py")


class RecordingSense:
    def __init__(self, real):
        self._real = real
        self.emits = []

    def format_line(self, *a, **k):
        return self._real.format_line(*a, **k)

    def emit(self, *a, **k):
        self.emits.append((a, k))
        return self._real.format_line(*a, **k)


class TestSliderSense(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.state_file = Path(self._tmp.name) / "state.json"
        spec = importlib.util.spec_from_file_location(
            "noobia_sense_real", AUTONOMY_DIR / "sense.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.recorder = RecordingSense(mod)
        self._orig_import = slider.import_sense
        slider.import_sense = lambda: self.recorder

    def tearDown(self):
        slider.import_sense = self._orig_import
        self._tmp.cleanup()

    def test_first_sample_baselines_quietly(self):
        res, code = slider.run(
            state_file=str(self.state_file),
            read_slider=lambda: "silent",
            now=1000,
        )
        self.assertEqual(code, 0)
        self.assertEqual(res["emitted"], [])
        self.assertEqual(res["state"]["position"], "silent")

    def test_transition_emits_p1_slider_change(self):
        # Sample 1: baseline silent
        slider.run(state_file=str(self.state_file), read_slider=lambda: "silent", now=1000)
        
        # Sample 2: switch to ring
        res, code = slider.run(state_file=str(self.state_file), read_slider=lambda: "ring", now=1002)
        self.assertEqual(code, 0)
        self.assertEqual(len(res["emitted"]), 1)
        line = res["emitted"][0]
        self.assertTrue(line.startswith("NOOBIA P1 body slider.change"))
        self.assertIn("to=ring", line)
        self.assertIn("from=silent", line)
        self.assertEqual(res["state"]["position"], "ring")

    def test_fixture_reading(self):
        fixture = HERE / "tools" / "tri_state_key" / "fixtures" / "tri-state-key-preflight-silent.json"
        if not fixture.exists():
            fixture = REPO / "lynx" / "tools" / "tri_state_key" / "fixtures" / "tri-state-key-preflight-silent.json"
        os.environ["LYNX_SLIDER_FIXTURE"] = str(fixture)
        try:
            pos = slider.read_hardware_slider()
            self.assertEqual(pos, "silent")
        finally:
            os.environ.pop("LYNX_SLIDER_FIXTURE", None)


if __name__ == "__main__":
    unittest.main()
