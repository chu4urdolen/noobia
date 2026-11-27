"""Unit test for config snapshot and restore drill (NA-70)."""

import tempfile
import unittest
from pathlib import Path
from lynx.tools.lynx_config_snapshot import create_snapshot, verify_restore_drill


class TestConfigSnapshot(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.conf1 = self.root / "noobia"
        self.conf1.mkdir()
        (self.conf1 / "autonomy.json").write_text('{"host": "lynx"}', encoding="utf-8")
        self.file1 = self.root / "patterns.json"
        self.file1.write_text('{"patterns": []}', encoding="utf-8")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_snapshot_and_restore_drill(self):
        archive = self.root / "test_snapshot.tar.gz"
        res = create_snapshot([self.conf1, self.file1], archive)
        self.assertTrue(res["ok"])
        self.assertTrue(archive.is_file())
        self.assertEqual(res["files_count"], 2)

        drill = verify_restore_drill(archive, res["manifest"])
        self.assertTrue(drill["ok"])
        self.assertTrue(drill["drill_passed"])
        self.assertEqual(drill["verified_files"], 2)


if __name__ == "__main__":
    unittest.main()
