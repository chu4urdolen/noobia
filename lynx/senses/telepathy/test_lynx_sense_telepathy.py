"""Tests for Lynx mesh telepathy sense (B4)."""

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


tele = _load("lynx_sense_telepathy", "telepathy/lynx_sense_telepathy.py")


class RecordingSense:
    def __init__(self, real):
        self._real = real
        self.emits = []

    def format_line(self, *a, **k):
        return self._real.format_line(*a, **k)

    def emit(self, *a, **k):
        self.emits.append((a, k))
        return self._real.format_line(*a, **k)


class TestTelepathySense(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.state_file = Path(self._tmp.name) / "state.json"
        spec = importlib.util.spec_from_file_location(
            "noobia_sense_real", AUTONOMY_DIR / "sense.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.recorder = RecordingSense(mod)
        self._orig_import = tele.import_sense
        tele.import_sense = lambda: self.recorder

    def tearDown(self):
        tele.import_sense = self._orig_import
        self._tmp.cleanup()

    def test_dushich_thinking_event(self):
        # Sample 1: Idle mesh
        tele.run(state_file=str(self.state_file), query_mesh=lambda: {"dushich_thinking": False}, now=1000)

        # Sample 2: Dushich begins thinking
        res, code = tele.run(
            state_file=str(self.state_file),
            query_mesh=lambda: {"dushich_thinking": True},
            now=1002,
        )
        self.assertEqual(code, 0)
        self.assertEqual(len(res["emitted"]), 1)
        line = res["emitted"][0]
        self.assertTrue(line.startswith("NOOBIA P1 mesh telepathy"))
        self.assertIn("friend=dushich", line)
        self.assertIn("state=thinking", line)

    def test_rose_singing_event(self):
        # Sample 1: Idle mesh
        tele.run(state_file=str(self.state_file), query_mesh=lambda: {"rose_singing": False}, now=1000)

        # Sample 2: Rose singing
        res, code = tele.run(
            state_file=str(self.state_file),
            query_mesh=lambda: {"rose_singing": True},
            now=1002,
        )
        self.assertEqual(code, 0)
        self.assertEqual(len(res["emitted"]), 1)
        line = res["emitted"][0]
        self.assertTrue(line.startswith("NOOBIA P1 mesh telepathy"))
        self.assertIn("friend=rose", line)
        self.assertIn("state=singing", line)

    def test_iris_motion_spotted(self):
        # Sample 1: Idle
        tele.run(state_file=str(self.state_file), query_mesh=lambda: {"iris_motion": False}, now=1000)

        # Sample 2: Iris spotted motion
        res, code = tele.run(
            state_file=str(self.state_file),
            query_mesh=lambda: {"iris_motion": True},
            now=1002,
        )
        self.assertEqual(code, 0)
        self.assertEqual(len(res["emitted"]), 1)
        line = res["emitted"][0]
        self.assertTrue(line.startswith("NOOBIA P1 mesh telepathy"))
        self.assertIn("friend=iris", line)
        self.assertIn("state=motion_spotted", line)


if __name__ == "__main__":
    unittest.main()
