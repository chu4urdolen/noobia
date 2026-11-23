#!/usr/bin/env python3
"""G3 motion gestures from synthetic 12.5 Hz accelerometer bursts."""
import math
import os
from pathlib import Path
import tempfile
import unittest

os.environ.setdefault("NOOBIA_AUTONOMY_DIR", "/noobia/common/autonomy")

from lynx.senses.motion import lynx_sense_motion as motion

G = motion.G_MM


def vec(tilt_deg, g=1.0):
    r = math.radians(tilt_deg)
    return [0, int(G * g * math.sin(r)), int(G * g * math.cos(r))]


class Gestures(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.sf = str(Path(self.tmp.name) / "state.json")
        self.lines = []
        self._emit = motion.emit_line
        motion.emit_line = lambda sense, p, s, event, fields=None, text="", dry_run=False: \
            f"NOOBIA P{p} {s} {event} " + " ".join(f"{k}={v}" for k, v in (fields or {}).items())

    def tearDown(self):
        motion.emit_line = self._emit
        self.tmp.cleanup()

    def step(self, now, samples):
        """samples: list of [x,y,z] taken 80 ms apart, ending at `now`."""
        n = len(samples)
        burst = [[now - (n - 1 - i) * 0.08] + list(s) for i, s in enumerate(samples)]
        res, code = motion.run(dry_run=False, state_file=self.sf, now=now,
                               reader=lambda: {"raw": samples[-1], "burst": burst})
        self.assertEqual(code, 0)
        got = [l.split()[3] for l in res["emitted"] if l.split()[3] not in ("status.sample", "position.change")]
        self.lines += got
        return got

    def still(self, now, tilt=0.0):
        return self.step(now, [vec(tilt, 1.0 + 0.002 * ((i % 3) - 1)) for i in range(9)])

    def test_freefall_once_with_cooldown(self):
        self.still(1000)
        drop = [vec(0)] * 3 + [vec(0, 0.1)] * 3 + [vec(0, 2.5)] + [vec(0)] * 2
        self.assertIn("freefall", self.step(1001, drop))
        self.assertNotIn("freefall", self.step(1002, drop), "cooldown 10 s")
        self.assertIn("freefall", self.step(1012, drop))

    def test_shaken(self):
        self.still(1000)
        shake = [vec(0, g) for g in (1.8, 0.4, 1.7, 1.0, 0.3, 1.9, 0.45, 1.6, 1.0)]
        got = self.step(1001, shake)
        self.assertIn("shaken", got)
        self.assertNotIn("freefall", got, "single low samples are not a drop")

    def test_mild_shake_counts(self):
        self.still(1000)
        mild = [vec(0, g) for g in (1.2, 0.82, 1.18, 1.0, 0.8, 1.0, 1.0, 1.0, 1.0)]
        self.assertIn("shaken", self.step(1001, mild))

    def test_resting_noise_is_not_a_shake(self):
        noise = [vec(0, g) for g in (1.0, 0.98, 1.09, 0.92, 1.05, 0.95, 1.03, 0.97, 1.0)]
        for s in range(30):
            self.assertNotIn("shaken", self.step(1000 + s, noise))

    def test_pickup_after_rest_then_placed(self):
        for s in range(0, 61):
            self.assertEqual(self.still(1000 + s), [])
        move = [vec(a) for a in (0, 10, 25, 40, 55, 65, 70, 72, 73)]
        self.assertEqual(self.step(1062, move), ["pickup"])
        for s in range(1, 16):
            self.assertEqual(self.still(1062 + s, 73), [], f"too early at {s} s")
        self.assertEqual(self.still(1062 + 16, 73), ["placed"])
        self.assertEqual(self.lines, ["pickup", "placed"])

    def test_no_pickup_without_rest_first(self):
        for s in range(5):
            self.still(1000 + s)
        move = [vec(a) for a in (0, 10, 25, 40, 55, 65, 70, 72, 73)]
        self.assertEqual(self.step(1006, move), [])

    def test_rocked_gently(self):
        got = []
        for s in range(12):
            t_end = 1000 + s
            samples = [vec(20 + 15 * math.sin(2 * math.pi * 0.6 * (t_end - (8 - i) * 0.08))) for i in range(9)]
            got += self.step(t_end, samples)
        self.assertIn("rocked", got)
        self.assertEqual(got.count("rocked"), 1, "cooldown 60 s")
        self.assertNotIn("shaken", got)
        self.assertNotIn("freefall", got)

    def test_holding_still_in_a_hand_is_quiet(self):
        for s in range(90):
            wobble = [vec(60 + 1.5 * math.sin(i + s), 1.0 + 0.01 * math.sin(3 * i)) for i in range(9)]
            self.assertEqual(self.step(1000 + s, wobble), [])

    def test_single_read_fallback_still_works(self):
        res, code = motion.run(dry_run=True, state_file=self.sf, now=1000, reader=lambda: {"raw": [0, 0, 9800]})
        self.assertEqual(code, 0)
        self.assertEqual(res["gestures"], [])


class BurstParsing(unittest.TestCase):
    def test_features(self):
        f = motion.burst_features([[i * 0.08] + vec(0) for i in range(9)])
        self.assertFalse(f["freefall"]); self.assertFalse(f["shaken"]); self.assertLess(f["jitter"], 50)


if __name__ == "__main__":
    unittest.main()
