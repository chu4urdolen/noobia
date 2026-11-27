#!/usr/bin/env python3
import json
from pathlib import Path
import tempfile
import unittest

from common.autonomy.sensekit.kit import Event, Sense, band, run_sense
from common.autonomy.sensekit.loop import SenseScheduler
from common.autonomy.sensekit.state import load_state, save_state


class TestSenseKit(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_state_persistence(self):
        p = self.root / "state.json"
        save_state(p, {"counter": 42})
        loaded = load_state(p)
        self.assertEqual(loaded.get("counter"), 42)

    def test_band_classification(self):
        levels = [("low", 10.0), ("mid", 20.0), ("high", None)]
        self.assertEqual(band(5.0, levels), "low")
        self.assertEqual(band(15.0, levels), "mid")
        self.assertEqual(band(25.0, levels), "high")
        # Hysteresis test
        self.assertEqual(band(10.5, levels, previous="low", hysteresis=1.0), "low")

    def test_run_sense_and_cooldown(self):
        def observe():
            return {"temp": 52.0}

        def detect(prev, obs, now):
            if obs["temp"] > 50.0:
                return [Event("overheat", fields={"val": obs["temp"]}, text="Too hot", cooldown_s=10.0)], {"last_seen": obs["temp"]}
            return [], {}

        state_file = str(self.root / "temp_state.json")
        # First sample: event emitted
        res, code = run_sense("thermal", observe, detect, dry_run=False, state_file=state_file, now=100.0)
        self.assertEqual(code, 0)
        self.assertEqual(len(res["emitted"]), 1)
        self.assertIn("overheat", res["emitted"][0])

        # Second sample within cooldown: event suppressed
        res2, code2 = run_sense("thermal", observe, detect, dry_run=False, state_file=state_file, now=105.0)
        self.assertEqual(code2, 0)
        self.assertEqual(len(res2["emitted"]), 0)

        # Third sample after cooldown: event emitted
        res3, code3 = run_sense("thermal", observe, detect, dry_run=False, state_file=state_file, now=111.0)
        self.assertEqual(code3, 0)
        self.assertEqual(len(res3["emitted"]), 1)

    def test_scheduler(self):
        sched = SenseScheduler()
        calls = []
        sched.register("dummy", lambda: calls.append(1), interval_s=1.0)
        sched.step(now=10.0)
        self.assertEqual(len(calls), 1)
        sched.step(now=10.5)
        self.assertEqual(len(calls), 1)
        sched.step(now=11.1)
        self.assertEqual(len(calls), 2)


if __name__ == "__main__":
    unittest.main()
