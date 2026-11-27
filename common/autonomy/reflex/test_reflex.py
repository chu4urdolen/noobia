"""Tests for common/autonomy/reflex/engine.py (NA-40)."""

import os
import stat
import tempfile
import unittest
from pathlib import Path

from common.autonomy.reflex.engine import ReflexEngine


class TestReflexEngine(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp_dir.name) / "reflexes.db"
        self.engine = ReflexEngine(self.db_path, noob_name="testlynx")

        # Create dummy script
        self.script_path = Path(self.tmp_dir.name) / "test_buzz.sh"
        self.script_path.write_text("#!/bin/sh\necho \"BUZZ: $1\"\n", encoding="utf-8")
        self.script_path.chmod(self.script_path.stat().st_mode | stat.S_IEXEC)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_add_and_execute_reflex_once(self):
        rule_id = self.engine.add_rule(r"touch\.tap", str(self.script_path), description="Buzz on tap")
        self.assertGreater(rule_id, 0)

        # Trigger on matching event
        res = self.engine.handle_event("ev-01", "NOOBIA P1 touch touch.tap | user tapped screen")
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["exit_code"], 0)
        self.assertIn("BUZZ: ev-01", res[0]["output"])

        # Second delivery of same event_id must NOT re-execute!
        res_dup = self.engine.handle_event("ev-01", "NOOBIA P1 touch touch.tap | user tapped screen")
        self.assertEqual(len(res_dup), 0)

    def test_self_trigger_guard(self):
        self.engine.add_rule(r"buzz", str(self.script_path))
        # Event caused by reflex itself must be ignored
        res = self.engine.handle_event("ev-02", "NOOBIA P1 haptic buzz cause=reflex | reflex vibration")
        self.assertEqual(len(res), 0)


if __name__ == "__main__":
    unittest.main()
