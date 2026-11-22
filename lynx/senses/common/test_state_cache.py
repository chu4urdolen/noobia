#!/usr/bin/env python3
"""Sense state is cached in memory and written to flash only when it matters."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lynx_senses_lib as lib  # noqa: E402


class StateCacheTest(unittest.TestCase):
    def setUp(self):
        lib._STATE_CACHE.clear()
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "motion" / "state.json"
        self.writes = 0
        real = lib._write_state

        def counting(path, data):
            self.writes += 1
            real(path, data)
        self.patch = mock.patch.object(lib, "_write_state", counting)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        lib._STATE_CACHE.clear()
        self.tmp.cleanup()

    def test_counter_only_changes_are_not_written(self):
        for i in range(30):
            lib.save_state(self.path, {"samples": i, "last_ts": 1000 + i, "position": "horizontal"})
        self.assertEqual(self.writes, 1)
        # The newest state is still what the next sample sees.
        self.assertEqual(lib.load_state(self.path)["samples"], 29)

    def test_meaningful_change_is_written_at_once(self):
        lib.save_state(self.path, {"samples": 1, "position": "horizontal", "candidate": None})
        lib.save_state(self.path, {"samples": 2, "position": "horizontal", "candidate": "vertical"})
        self.assertEqual(self.writes, 2)
        self.assertEqual(lib.load_state(self.path)["candidate"], "vertical")

    def test_flushes_at_least_once_a_minute(self):
        t = [1000.0]
        with mock.patch.object(lib.time, "monotonic", lambda: t[0]):
            lib.save_state(self.path, {"samples": 1, "position": "horizontal"})
            t[0] += 59
            lib.save_state(self.path, {"samples": 60, "position": "horizontal"})
            self.assertEqual(self.writes, 1)
            t[0] += 2
            lib.save_state(self.path, {"samples": 62, "position": "horizontal"})
            self.assertEqual(self.writes, 2)
        # A fresh process (empty cache) reads the flushed file.
        lib._STATE_CACHE.clear()
        self.assertEqual(lib.load_state(self.path)["samples"], 62)

    def test_load_returns_a_private_copy(self):
        lib.save_state(self.path, {"samples": 1, "nested": {"a": 1}})
        got = lib.load_state(self.path)
        got["nested"]["a"] = 99
        self.assertEqual(lib.load_state(self.path)["nested"]["a"], 1)


if __name__ == "__main__":
    unittest.main()
