#!/usr/bin/env python3
"""Unit tests for nexus_startup.corner_terminals."""

import unittest

from nexus_startup.corner_terminals import (
    CORNERS,
    CORNER_SPECS,
    build_autostart_desktop,
    build_gnome_terminal_command,
    compute_corner_rects,
    launch_missing_corners,
)


class TestCornerTerminals(unittest.TestCase):
    def test_compute_rects_even(self):
        work = {"x": 0, "y": 0, "width": 1920, "height": 1080}
        rects = compute_corner_rects(work)
        self.assertEqual(rects["topleft"], {"x": 0, "y": 0, "width": 960, "height": 540})
        self.assertEqual(rects["topright"], {"x": 960, "y": 0, "width": 960, "height": 540})
        self.assertEqual(rects["bottomleft"], {"x": 0, "y": 540, "width": 960, "height": 540})
        self.assertEqual(rects["bottomright"], {"x": 960, "y": 540, "width": 960, "height": 540})

    def test_compute_rects_odd_with_offset(self):
        work = {"x": 67, "y": 32, "width": 1853, "height": 1048}
        rects = compute_corner_rects(work)
        self.assertEqual(rects["topleft"], {"x": 67, "y": 32, "width": 926, "height": 524})
        self.assertEqual(rects["topright"], {"x": 993, "y": 32, "width": 927, "height": 524})
        self.assertEqual(rects["bottomleft"], {"x": 67, "y": 556, "width": 926, "height": 524})
        self.assertEqual(rects["bottomright"], {"x": 993, "y": 556, "width": 927, "height": 524})

    def test_build_gnome_terminal_command(self):
        for corner in CORNERS:
            cmd = build_gnome_terminal_command(corner)
            self.assertEqual(cmd[0], "/usr/bin/gnome-terminal")
            self.assertIn("--window", cmd)
            self.assertIn(f"--role={CORNER_SPECS[corner]['role']}", cmd)
            self.assertIn(f"--title={CORNER_SPECS[corner]['title']}", cmd)
            self.assertIn(f"--geometry={CORNER_SPECS[corner]['geometry']}", cmd)
            if CORNER_SPECS[corner]["command"] is not None:
                self.assertIn("--", cmd)
                shell_cmd = cmd[-1]
                self.assertIn(CORNER_SPECS[corner]["command"], shell_cmd)
                self.assertIn("exec /bin/bash -i", shell_cmd)
            else:
                self.assertNotIn("--", cmd)

    def test_build_autostart_desktop_5s_delay(self):
        desktop = build_autostart_desktop("/noobia/tools/nexus-corner-terminals.py")
        self.assertIn("[Desktop Entry]", desktop)
        self.assertIn("Name=Noobia Corner Terminals", desktop)
        self.assertIn("Exec=/usr/bin/python3 /noobia/tools/nexus-corner-terminals.py --delay 5", desktop)
        self.assertIn("X-GNOME-Autostart-enabled=true", desktop)
        self.assertIn("X-GNOME-Autostart-Delay=5", desktop)

    def test_launch_missing_corners_dry_run(self):
        existing = {CORNER_SPECS["topleft"]["role"], CORNER_SPECS["bottomright"]["role"]}
        cmds = launch_missing_corners(existing, dry_run=True)
        self.assertEqual(len(cmds), 2)
        flat = [" ".join(c) for c in cmds]
        self.assertTrue(any("noobia-corner-topright" in s for s in flat))
        self.assertTrue(any("noobia-corner-bottomleft" in s for s in flat))


if __name__ == "__main__":
    unittest.main()
