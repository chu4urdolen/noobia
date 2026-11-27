"""Unit tests for Profile system (NA-80)."""

import json
import tempfile
import unittest
from pathlib import Path
from common.autonomy.profile import Profile, WindowConfig


class TestProfile(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.file_path = Path(self.temp_dir.name) / "noob.json"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_save_and_load_profile(self):
        prof = Profile(
            name="argus",
            timezone="Europe/Sofia",
            paths={"events": "/var/lib/noobia/autonomy/events.db"},
            senses=["power", "network"],
            tool_dir="/usr/local/share/argus/tools",
            window=WindowConfig(window_s=45.0, max_lines=10)
        )
        prof.save(self.file_path)
        self.assertTrue(self.file_path.is_file())

        loaded = Profile.load(self.file_path)
        self.assertEqual(loaded.name, "argus")
        self.assertEqual(loaded.timezone, "Europe/Sofia")
        self.assertEqual(loaded.senses, ["power", "network"])
        self.assertEqual(loaded.window.window_s, 45.0)
        self.assertEqual(loaded.window.max_lines, 10)

    def test_fallback_when_missing(self):
        loaded = Profile.load(self.temp_dir.name + "/nonexistent.json")
        self.assertIn(loaded.name, ("lynx", "argus"))


if __name__ == "__main__":
    unittest.main()
