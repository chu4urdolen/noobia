"""Unit tests for solo_avatar/dushich_window.py."""

import json
import subprocess
import tempfile
import sys
import unittest
from pathlib import Path

from dushich_window import compute_sidebar_layout, is_dushich_helper_working
from avatar_pane import REQUIRED_FRAMES

HERE = Path(__file__).resolve().parent
PICS = Path("/noobia/pics")


class TestComputeSidebarLayout(unittest.TestCase):
    def test_quarter_screen_height(self):
        layout = compute_sidebar_layout(180, 180)
        self.assertEqual(
            layout,
            {
                "top_w": 180, "top_h": 180,
                "helper_w": 180, "helper_h": 0,
                "bottom_w": 180, "bottom_h": 0,
            },
        )

    def test_fullscreen_height(self):
        layout = compute_sidebar_layout(180, 720)
        self.assertEqual(
            layout,
            {
                "top_w": 180, "top_h": 270,
                "helper_w": 180, "helper_h": 0,
                "bottom_w": 180, "bottom_h": 450,
            },
        )

    def test_small_and_degenerate_values(self):
        self.assertEqual(
            compute_sidebar_layout(0, 5),
            {
                "top_w": 1, "top_h": 2,
                "helper_w": 1, "helper_h": 0,
                "bottom_w": 1, "bottom_h": 3,
            },
        )

    def test_aspect_ratio_is_respected(self):
        layout = compute_sidebar_layout(100, 500, aspect_ratio=2.0)
        self.assertEqual(layout["top_h"], 200)
        self.assertEqual(layout["bottom_h"], 300)

    def test_helper_quarter_screen_splits_evenly(self):
        layout = compute_sidebar_layout(180, 480, has_helper=True)
        self.assertEqual(
            layout,
            {
                "top_w": 180, "top_h": 240,
                "helper_w": 180, "helper_h": 240,
                "bottom_w": 180, "bottom_h": 0,
            },
        )

    def test_helper_fullscreen_keeps_rose_below(self):
        layout = compute_sidebar_layout(180, 1000, has_helper=True)
        self.assertEqual(
            layout,
            {
                "top_w": 180, "top_h": 270,
                "helper_w": 180, "helper_h": 270,
                "bottom_w": 180, "bottom_h": 460,
            },
        )

    def test_helper_shorter_than_two_ideals(self):
        layout = compute_sidebar_layout(180, 300, has_helper=True)
        self.assertEqual(layout["top_h"], 150)
        self.assertEqual(layout["helper_h"], 150)
        self.assertEqual(layout["bottom_h"], 0)


class TestIsDushichHelperWorking(unittest.TestCase):
    def test_working_pane_text(self):
        self.assertTrue(
            is_dushich_helper_working(
                "esc to interrupt",
                bridge_dir="/nonexistent-bridge",
                banshee_runs_dir="/nonexistent-runs",
            )
        )

    def test_idle_pane_and_no_active_states(self):
        self.assertFalse(
            is_dushich_helper_working(
                "Ask Codex",
                bridge_dir="/nonexistent-bridge",
                banshee_runs_dir="/nonexistent-runs",
            )
        )

    def test_bridge_state_running(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / "20260101T000000Z-abc123"
            run.mkdir()
            (run / "state.json").write_text(json.dumps({"status": "running"}))
            self.assertTrue(
                is_dushich_helper_working(
                    bridge_dir=tmp, banshee_runs_dir="/nonexistent-runs"
                )
            )

    def test_banshee_task_runs_queued(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / "20260101T000000Z-abc123"
            run.mkdir()
            (run / "state.json").write_text(json.dumps({"status": "queued"}))
            self.assertTrue(
                is_dushich_helper_working(
                    bridge_dir="/nonexistent-bridge", banshee_runs_dir=tmp
                )
            )

    def test_done_status_is_not_working(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / "20260101T000000Z-abc123"
            run.mkdir()
            (run / "state.json").write_text(json.dumps({"status": "done"}))
            self.assertFalse(
                is_dushich_helper_working(
                    bridge_dir="/nonexistent-bridge", banshee_runs_dir=tmp
                )
            )

    def test_corrupt_state_json_is_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / "20260101T000000Z-abc123"
            run.mkdir()
            (run / "state.json").write_text("not json {")
            self.assertFalse(
                is_dushich_helper_working(
                    bridge_dir="/nonexistent-bridge", banshee_runs_dir=tmp
                )
            )


class TestFramePixbufs(unittest.TestCase):
    def setUp(self):
        try:
            import gi

            gi.require_version("GdkPixbuf", "2.0")
            from gi.repository import GdkPixbuf

            self.GdkPixbuf = GdkPixbuf
        except Exception as exc:  # pragma: no cover
            self.skipTest(f"GdkPixbuf unavailable: {exc}")

    def test_all_agent_frames_load_at_180x270(self):
        for agent in ("Aria", "Banshee", "Dushich"):
            for frame in REQUIRED_FRAMES:
                with self.subTest(agent=agent, frame=frame):
                    png = PICS / agent / f"{frame}.png"
                    self.assertTrue(png.exists(), str(png))
                    pixbuf = self.GdkPixbuf.Pixbuf.new_from_file_at_scale(
                        str(png), 180, 270, False
                    )
                    self.assertIsInstance(pixbuf, self.GdkPixbuf.Pixbuf)
                    self.assertEqual(
                        (pixbuf.get_width(), pixbuf.get_height()), (180, 270)
                    )


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
