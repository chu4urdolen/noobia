"""Unit tests for solo_avatar/nexus_forge.py."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from nexus_forge import (
    DEFAULT_QUADRANTS,
    build_quadrants_table,
    load_config,
    quadrant_names,
    resolve_token_badge,
)

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
        self.assertEqual(q.get("badge"), "Local: 100%")
        self.assertIn("/dushich/solo/launch", q["command"][-1])

    def test_top_right_is_banshee_plus_dushich(self):
        q = DEFAULT_QUADRANTS["top_right"]
        self.assertEqual(q["title"], "Banshee + Dushich Helper")
        self.assertEqual(q["agent"], "Banshee")
        self.assertEqual(q["helper_agent"], "")
        self.assertIn("/banshee/launch", q["command"][-1])

    def test_bottom_right_is_gwyn_app_nub(self):
        q = DEFAULT_QUADRANTS["bottom_right"]
        self.assertEqual(q["title"], "Gwyn + Dushich Helper")
        self.assertEqual(q["agent"], "Gwyn")
        self.assertEqual(q["helper_agent"], "")
        self.assertIn("/gwyn-app-nub/launch", q["command"][-1])

    def test_every_command_is_a_nonempty_list(self):
        for name, q in DEFAULT_QUADRANTS.items():
            with self.subTest(name=name):
                self.assertIsInstance(q["command"], list)
                self.assertTrue(len(q["command"]) >= 1)
                self.assertIn(q["agent"], ("", "Aria", "Banshee", "Dushich", "Gwyn"))
                self.assertEqual(q["helper_agent"], "")

    def test_quadrant_names_default_vs_left_only(self):
        self.assertEqual(
            quadrant_names(),
            ["top_left", "top_right", "bottom_left", "bottom_right"],
        )
        self.assertEqual(
            quadrant_names(left_only=True),
            ["top_left", "bottom_left"],
        )


class TestConfigAndBadges(unittest.TestCase):
    def test_load_config_none_or_missing(self):
        self.assertEqual(load_config(None, check_default=False), {})
        self.assertEqual(load_config("/nonexistent/nexus-forge-cfg.json"), {})

    def test_load_config_valid_and_invalid_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            good_file = Path(tmpdir) / "config.json"
            good_file.write_text('{"title": "Custom Forge", "interval": 0.5}', encoding="utf-8")
            cfg = load_config(good_file)
            self.assertEqual(cfg.get("title"), "Custom Forge")
            self.assertEqual(cfg.get("interval"), 0.5)

            bad_file = Path(tmpdir) / "corrupt.json"
            bad_file.write_text('{invalid_json', encoding="utf-8")
            self.assertEqual(load_config(bad_file), {})

    def test_build_quadrants_table_overrides(self):
        custom = {
            "quadrants": {
                "top_left": {
                    "title": "My Term",
                    "command": ["/usr/bin/htop"],
                    "badge": "CPU: 12%",
                }
            }
        }
        table = build_quadrants_table(custom)
        self.assertEqual(table["top_left"]["title"], "My Term")
        self.assertEqual(table["top_left"]["command"], ["/usr/bin/htop"])
        self.assertEqual(table["top_left"]["badge"], "CPU: 12%")
        # Other quadrants remain unchanged
        self.assertEqual(table["bottom_left"]["title"], "Dushich Solo")

    def test_resolve_token_badge(self):
        # 1. Explicit badge takes precedence
        self.assertEqual(
            resolve_token_badge("Aria", explicit_badge="Custom: 99%"),
            "Custom: 99%",
        )
        # 2. Local Dushich
        self.assertEqual(resolve_token_badge("Dushich"), "Local: 100%")
        self.assertEqual(resolve_token_badge("dushich"), "Local: 100%")

        # 3. Cache file override
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = Path(tmpdir) / "rate_limits.json"
            cache.write_text(json.dumps({"Gwyn": "H/W: 45% / 80%"}), encoding="utf-8")
            self.assertEqual(
                resolve_token_badge("Gwyn", rate_limits_path=cache),
                "H/W: 45% / 80%",
            )

        # 4. Unknown agent fallback
        self.assertEqual(resolve_token_badge("UnknownAgent"), "H/W: --% / --%")
        self.assertEqual(resolve_token_badge(""), "H/W: --% / --%")


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
