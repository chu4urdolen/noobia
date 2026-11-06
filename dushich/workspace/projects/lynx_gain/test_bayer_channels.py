import unittest
from pathlib import Path

from bayer_channels import bggr_channel_stats


class TestBayerChannels(unittest.TestCase):
    def test_basic_4x4_default(self):
        # 4x4 BGGR pattern with known values
        # Row 0: B G1 B G1
        # Row 1: G2 R G2 R
        # Row 2: B G1 B G1
        # Row 3: G2 R G2 R
        values = [
            10, 20, 30, 40,
            50, 60, 70, 80,
            90, 100, 110, 120,
            130, 140, 150, 160,
        ]
        frame = bytes(values)
        stats = bggr_channel_stats(frame, 4, 4)
        # Each channel appears exactly 4 times
        for name in ["B", "G1", "G2", "R"]:
            self.assertEqual(stats[name]["count"], 4)
        # Verify min/max/mean for one channel
        self.assertEqual(stats["B"]["min"], 10)
        self.assertEqual(stats["B"]["max"], 110)
        self.assertAlmostEqual(stats["B"]["mean"], 60.0)

    def test_invalid_dimensions(self):
        frame = bytes(8)
        with self.assertRaises(ValueError):
            bggr_channel_stats(frame, 3, 2)  # odd width
        with self.assertRaises(ValueError):
            bggr_channel_stats(frame, 2, 3)  # odd height
        with self.assertRaises(ValueError):
            bggr_channel_stats(frame, 2, 2)  # size mismatch

    def test_rggb_phase(self):
        # Use same frame; in rggb pattern B and R are swapped
        values = [
            10, 20, 30, 40,
            50, 60, 70, 80,
            90, 100, 110, 120,
            130, 140, 150, 160,
        ]
        frame = bytes(values)
        stats = bggr_channel_stats(frame, 4, 4, phase="rggb")
        # In rggb, B channel positions are swapped; expect min=60, max=160, mean=110
        self.assertEqual(stats["B"]["min"], 60)
        self.assertEqual(stats["B"]["max"], 160)
        self.assertAlmostEqual(stats["B"]["mean"], 110.0)

    def test_invalid_phase(self):
        values = [10, 20, 30, 40]
        frame = bytes(values)
        with self.assertRaises(ValueError):
            bggr_channel_stats(frame, 2, 2, phase="invalid")


if __name__ == "__main__":
    unittest.main()

