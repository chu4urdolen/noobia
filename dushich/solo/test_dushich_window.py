"""Unit tests for solo_avatar/dushich_window.py."""

import subprocess
import sys
import unittest
from pathlib import Path

from dushich_window import compute_sidebar_layout
from avatar_pane import REQUIRED_FRAMES

HERE = Path(__file__).resolve().parent
FRAMES_DIR = Path("/noobia/pics/Dushich")


class TestComputeSidebarLayout(unittest.TestCase):
    def test_quarter_screen_height(self):
        layout = compute_sidebar_layout(180, 180)
        self.assertEqual(
            layout,
            {"top_w": 180, "top_h": 180, "bottom_w": 180, "bottom_h": 0},
        )

    def test_fullscreen_height(self):
        layout = compute_sidebar_layout(180, 720)
        self.assertEqual(
            layout,
            {"top_w": 180, "top_h": 270, "bottom_w": 180, "bottom_h": 450},
        )

    def test_small_and_degenerate_values(self):
        self.assertEqual(
            compute_sidebar_layout(0, 5),
            {"top_w": 1, "top_h": 2, "bottom_w": 1, "bottom_h": 3},
        )
        self.assertEqual(
            compute_sidebar_layout(100, 10),
            {"top_w": 100, "top_h": 10, "bottom_w": 100, "bottom_h": 0},
        )

    def test_aspect_ratio_is_respected(self):
        layout = compute_sidebar_layout(100, 500, aspect_ratio=2.0)
        self.assertEqual(layout["top_h"], 200)
        self.assertEqual(layout["bottom_h"], 300)


class TestFramePixbufs(unittest.TestCase):
    def setUp(self):
        try:
            import gi

            gi.require_version("GdkPixbuf", "2.0")
            from gi.repository import GdkPixbuf

            self.GdkPixbuf = GdkPixbuf
        except Exception as exc:  # pragma: no cover
            self.skipTest(f"GdkPixbuf unavailable: {exc}")

    def test_all_six_frames_load_at_180x270(self):
        for frame in REQUIRED_FRAMES:
            with self.subTest(frame=frame):
                png = FRAMES_DIR / f"{frame}.png"
                self.assertTrue(png.exists(), str(png))
                pixbuf = self.GdkPixbuf.Pixbuf.new_from_file_at_scale(
                    str(png), 180, 270, False
                )
                self.assertIsInstance(pixbuf, self.GdkPixbuf.Pixbuf)
                self.assertEqual((pixbuf.get_width(), pixbuf.get_height()), (180, 270))


class TestSelfTestFlag(unittest.TestCase):
    def test_self_test_exits_zero(self):
        result = subprocess.run(
            [sys.executable, str(HERE / "dushich_window.py"), "--self-test"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("self-test OK", result.stdout)


if __name__ == "__main__":
    unittest.main()
