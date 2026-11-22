#!/usr/bin/env python3
"""The camera keeper prepares once per boot and can never cause a boot loop."""
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lynx_camera_keeper as k  # noqa: E402


class KeeperTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = mock.patch.object(k, "STATE", Path(self.tmp.name))
        self.p.start()
        self.prepared = []

    def tearDown(self):
        self.p.stop()
        self.tmp.cleanup()

    def lynx_says(self, boot="b1", uptime=600, prepared="NOT_PREPARED", healthy="HEALTHY", safe="SAFE_WATCHERS"):
        return lambda cmd: f"{boot}\n{uptime}\n{prepared}\n{healthy}\n{safe}\n"

    def prep(self, state="prepared_no_stream"):
        def f():
            self.prepared.append(1)
            return {"state": state, "error": None if state.startswith("prep") else "boom"}
        return f

    def test_prepares_once_per_boot(self):
        self.assertEqual(k.decide(self.lynx_says(), self.prep()), "prepared")
        self.assertEqual(k.decide(self.lynx_says(), self.prep()), "already-done")
        self.assertEqual(len(self.prepared), 1)

    def test_waits_for_settle_and_health(self):
        self.assertEqual(k.decide(self.lynx_says(uptime=100), self.prep()), "settling")
        self.assertEqual(k.decide(self.lynx_says(healthy="UNHEALTHY"), self.prep()), "waiting-for-health")
        self.assertEqual(self.prepared, [])

    def test_failure_is_not_retried_in_the_same_boot(self):
        self.assertEqual(k.decide(self.lynx_says(), self.prep("failed")), "failed")
        self.assertEqual(k.decide(self.lynx_says(), self.prep()), "already-failed")
        self.assertEqual(len(self.prepared), 1)
        # A failed (but finished) preparation does not block the next boot.
        self.assertEqual(k.decide(self.lynx_says(boot="b2"), self.prep()), "prepared")

    def test_crash_during_preparation_skips_the_next_boot(self):
        def crash():
            self.prepared.append(1)
            raise SystemExit("Lynx vanished mid-preparation")   # keeper never writes done/failed
        with self.assertRaises(SystemExit):
            k.decide(self.lynx_says(boot="b1"), crash)
        time.sleep(0.01)
        self.assertEqual(k.decide(self.lynx_says(boot="b2"), self.prep()), "skipped-after-interrupted")
        self.assertEqual(k.decide(self.lynx_says(boot="b2"), self.prep()), "already-skipped")
        self.assertEqual(len(self.prepared), 1, "no preparation after a crash during one")
        # A person clears it: delete the interrupted boot's marker -> the next boot prepares.
        (k.STATE / "b1.started").unlink()
        self.assertEqual(k.decide(self.lynx_says(boot="b3"), self.prep()), "prepared")

    def test_never_prepares_while_original_watchers_run(self):
        self.assertEqual(k.decide(self.lynx_says(safe="UNSAFE_WATCHERS"), self.prep()), "waiting-for-safe-watchers")
        self.assertEqual(self.prepared, [])
        self.assertEqual(k.decide(self.lynx_says(), self.prep()), "prepared")

    def test_already_prepared_by_hand(self):
        self.assertEqual(k.decide(self.lynx_says(prepared="PREPARED"), self.prep()), "already-prepared")
        self.assertEqual(self.prepared, [])

    def test_unreachable_and_disabled(self):
        self.assertEqual(k.decide(lambda cmd: None, self.prep()), "unreachable")
        (k.STATE / "disable").write_text("")
        self.assertEqual(k.decide(self.lynx_says(), self.prep()), "disabled")
        self.assertEqual(self.prepared, [])


if __name__ == "__main__":
    unittest.main()
