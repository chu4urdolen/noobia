"""Unit tests for solo_avatar/avatar_pane.py."""

import unittest

from avatar_pane import (
    BRAILLE_SPINNERS,
    REQUIRED_FRAMES,
    detect_solo_state,
    render_png_halfblocks,
    select_frame_name,
)

IDLE_PNG = "/noobia/pics/Dushich/idle.png"


class TestRequiredFrames(unittest.TestCase):
    def test_frames_contain_all_states(self):
        self.assertEqual(
            REQUIRED_FRAMES,
            ("idle", "working_1", "working_2", "working_3", "working_4", "final"),
        )

    def test_braille_spinners_are_braille_chars(self):
        self.assertEqual(len(BRAILLE_SPINNERS), 10)
        self.assertIn("⠋", BRAILLE_SPINNERS)


class TestDetectSoloState(unittest.TestCase):
    def test_idle(self):
        self.assertEqual(detect_solo_state("Ask Codex anything"), "idle")
        self.assertEqual(detect_solo_state(""), "idle")

    def test_working_by_interrupt_hint(self):
        self.assertEqual(detect_solo_state("esc to interrupt"), "working")

    def test_working_by_braille_spinner_in_text(self):
        self.assertEqual(detect_solo_state("thinking ⠹ now"), "working")

    def test_working_by_braille_spinner_in_title(self):
        self.assertEqual(detect_solo_state("status…", "⠦ watchmaker"), "working")

    def test_final(self):
        self.assertEqual(detect_solo_state("Worked for 5s"), "final")

    def test_working_beats_final(self):
        self.assertEqual(
            detect_solo_state("esc to interrupt — Worked for 5s"), "working"
        )


class TestSelectFrameName(unittest.TestCase):
    def test_working_cycles_four_frames(self):
        self.assertEqual(
            [select_frame_name("working", i) for i in range(4)],
            ["working_1", "working_2", "working_3", "working_4"],
        )

    def test_working_wraps_around(self):
        self.assertEqual(select_frame_name("working", 7), "working_4")
        self.assertEqual(select_frame_name("working", 8), "working_1")

    def test_final(self):
        self.assertEqual(select_frame_name("final", 3), "final")

    def test_idle_fallback(self):
        self.assertEqual(select_frame_name("idle", 3), "idle")
        self.assertEqual(select_frame_name("unknown", 0), "idle")


class TestRenderPngHalfblocks(unittest.TestCase):
    def test_default_size_gives_14_lines(self):
        art = render_png_halfblocks(IDLE_PNG)
        lines = art.splitlines()
        self.assertEqual(len(lines), 14)

    def test_each_line_is_28_halfblocks_with_reset(self):
        art = render_png_halfblocks(IDLE_PNG, 28)
        for line in art.splitlines():
            self.assertEqual(line.count("▀"), 28)
            self.assertTrue(line.endswith("\033[0m"))
            self.assertIn("\033[38;2;", line)
            self.assertIn("\033[48;2;", line)

    def test_odd_size_is_evened_out(self):
        art = render_png_halfblocks(IDLE_PNG, 27)
        self.assertEqual(len(art.splitlines()), 13)

    def test_min_size_floors_at_2(self):
        art = render_png_halfblocks(IDLE_PNG, 1)
        self.assertEqual(len(art.splitlines()), 1)


if __name__ == "__main__":
    unittest.main()
