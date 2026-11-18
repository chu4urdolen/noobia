"""Unit tests for solo_avatar/nexus_forge.py."""

import subprocess
import sys
import unittest
from pathlib import Path

from nexus_forge import DEFAULT_QUADRANTS, quadrant_names

HERE = Path(__file__).resolve().parent
MODULE = HERE / "nexus_forge.py"


class TestDefaultQuadrants(unittest.TestCase):
    def test_expects_exactly_four_named_quadrants(self):
        self.assertEqual(
            set(DEFAULT_QUADRANTS),
            {"top_left", "bottom_left", "top_right", "bottom_right"},
        )

    def test_top_left_is_aria_plus_dushich(self):
        q = DEFAULT_QUADRANTS["top_left"]
        self.assertEqual(q["title"], "Aria + Dushich Helper")
        self.assertEqual(q["agent"], "Aria")
        self.assertEqual(q["helper_agent"], "")
        self.assertTrue(q["command"])
        self.assertIn("codex-with-dushich", q["command"][-1])

    def test_bottom_left_is_dushich_solo(self):
        q = DEFAULT_QUADRANTS["bottom_left"]
        self.assertEqual(q["title"], "Dushich Solo")
        self.assertEqual(q["agent"], "Dushich")
        self.assertEqual(q["helper_agent"], "")
        self.assertIn("/usr/local/bin/dushich", q["command"][-1])

    def test_top_right_is_banshee_plus_dushich(self):
        q = DEFAULT_QUADRANTS["top_right"]
        self.assertEqual(q["title"], "Banshee + Dushich Helper")
        self.assertEqual(q["agent"], "Banshee")
        self.assertEqual(q["helper_agent"], "")
        self.assertIn("/noobia/banshee/launch", q["command"][-1])

    def test_bottom_right_is_gwyn_app_nub(self):
        q = DEFAULT_QUADRANTS["bottom_right"]
        self.assertEqual(q["title"], "Gwyn App Nub")
        self.assertEqual(q["agent"], "Gwyn")
        self.assertEqual(q["helper_agent"], "")
        self.assertIn("/noobia/gwyn-app-nub/launch", q["command"][-1])

    def test_every_command_is_a_nonempty_list(self):
        for name, q in DEFAULT_QUADRANTS.items():
            with self.subTest(name=name):
                self.assertIsInstance(q["command"], list)
                self.assertTrue(len(q["command"]) >= 1)
                self.assertIn(q["agent"], ("", "Aria", "Banshee", "Dushich", "Gwyn"))
                self.assertEqual(q["helper_agent"], "")

    def test_quadrant_names_default_vs_left_only(self):
        self.assertEqual(quadrant_names(), [
            "top_left", "top_right", "bottom_left", "bottom_right",
        ])
        self.assertEqual(quadrant_names(left_only=True), [
            "top_left", "bottom_left",
        ])


class TestSelfTest(unittest.TestCase):
    def test_self_test_exits_zero_and_reports_ok(self):
        proc = subprocess.run(
            [sys.executable, str(MODULE), "--self-test"],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(HERE),
        )
        self.assertEqual(proc.returncode, 0, f"stderr: {proc.stderr}")
        self.assertIn("self-test OK", proc.stdout)


if __name__ == "__main__":
    unittest.main()
