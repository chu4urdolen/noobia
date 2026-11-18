"""Unit tests for solo_avatar/avatar_pane.py."""

import io
import re
import unittest
from contextlib import redirect_stdout

from avatar_pane import (
    BRAILLE_SPINNERS,
    REQUIRED_FRAMES,
    StateTracker,
    detect_solo_state,
    draw_frame,
    is_pane_working,
    render_png_chafa,
    render_png_halfblocks,
    select_frame_name,
)

IDLE_PNG = "/noobia/pics/Dushich/idle.png"
ANSI_RE = re.compile(r"\033\[[0-9;?]*[A-Za-z]")


def strip_art(text: str) -> str:
    """Remove ANSI escape sequences, half-blocks, and newlines."""
    text = ANSI_RE.sub("", text)
    return text.replace("▀", "").replace("\n", "").replace("\r", "")


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

    def test_is_pane_working_reflects_state(self):
        self.assertTrue(is_pane_working("esc to interrupt"))
        self.assertFalse(is_pane_working("Ask Codex"))
        self.assertFalse(is_pane_working("Worked for 5s"))


class TestStateTracker(unittest.TestCase):
    def test_idle_until_work_starts(self):
        t = StateTracker()
        self.assertFalse(t.was_working)
        self.assertEqual(t.final_until, 0.0)
        self.assertEqual(t.update(False, 0.0), "idle")

    def test_working_holds_while_working(self):
        t = StateTracker()
        self.assertEqual(t.update(True, 1.0), "working")
        self.assertTrue(t.was_working)
        self.assertEqual(t.update(True, 2.0), "working")

    def test_final_holds_for_two_seconds_then_idle(self):
        t = StateTracker()
        t.update(True, 1.0)
        # Work stops at t=3 -> final, holds until t<5.
        self.assertEqual(t.update(False, 3.0), "final")
        self.assertFalse(t.was_working)
        self.assertEqual(t.final_until, 5.0)
        self.assertEqual(t.update(False, 4.0), "final")
        self.assertEqual(t.update(False, 4.99), "final")
        # At and after expiry, back to idle and stays idle.
        self.assertEqual(t.update(False, 5.0), "idle")
        self.assertEqual(t.update(False, 100.0), "idle")

    def test_new_work_after_idle_resets_to_working(self):
        t = StateTracker()
        t.update(True, 1.0)
        t.update(False, 2.0)  # final until 4.0
        t.update(False, 5.0)  # idle
        self.assertEqual(t.update(True, 6.0), "working")


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
    def test_default_size_gives_9_lines(self):
        art = render_png_halfblocks(IDLE_PNG)
        self.assertEqual(len(art.splitlines()), 9)

    def test_each_line_is_width_halfblocks_with_reset(self):
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

    def test_height_px_controls_lines(self):
        art = render_png_halfblocks(IDLE_PNG, 18, height_px=40)
        self.assertEqual(len(art.splitlines()), 20)
        for line in art.splitlines():
            self.assertEqual(line.count("▀"), 18)

    def test_odd_height_px_is_evened_out(self):
        art = render_png_halfblocks(IDLE_PNG, 18, height_px=41)
        self.assertEqual(len(art.splitlines()), 20)


class TestRenderPngChafa(unittest.TestCase):
    def test_render_png_chafa_preserves_portrait_rows(self):
        art = render_png_chafa("/noobia/pics/Dushich/idle.png", 18)
        self.assertEqual(len(art.splitlines()), 14)


class TestDrawFrame(unittest.TestCase):
    def test_outputs_no_text_labels(self):
        top = "\033[38;2;1;2;3m\033[48;2;4;5;6m▀" + "▀" * 3 + "\033[0m"
        buf = io.StringIO()
        with redirect_stdout(buf):
            draw_frame(top)
        out = buf.getvalue()
        # Only ANSI sequences, half-blocks, and newlines may remain.
        self.assertEqual(strip_art(out), "")
        for label in ("Dushich", "IDLE", "WORKING", "FINAL", "•"):
            self.assertNotIn(label, out)
        self.assertTrue(out.startswith("\033[?7l\033[?25l"))
        self.assertIn("\033[H", out)
        self.assertTrue(out.endswith("\033[J"))

    def test_bottom_art_is_drawn_below(self):
        top = "▀\033[0m"
        bottom = "▀▀\033[0m"
        buf = io.StringIO()
        with redirect_stdout(buf):
            draw_frame(top, bottom)
        out = buf.getvalue()
        self.assertIn(top + "\n" + bottom, out)

    def test_clear_all_uses_full_screen_clear(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            draw_frame("▀\033[0m", clear_all=True)
        out = buf.getvalue()
        self.assertIn("\033[2J\033[3J\033[H", out)
        self.assertNotIn("\033[J", out)


if __name__ == "__main__":
    unittest.main()
