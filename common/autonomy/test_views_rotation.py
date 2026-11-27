"""Unit test for BusyBox log rotation recovery (NA-11)."""

import tempfile
import unittest
from pathlib import Path
from common.autonomy.views import ViewReader


class TestViewsRotation(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.log_file = Path(self.temp_dir.name) / "messages"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_rotation_survives_without_loss(self):
        # 1. Write initial lines to messages
        self.log_file.write_text(
            "Nov 27 12:00:00 lynx daemon.info noobia-sense: NOOBIA P1 battery level=95\n"
            "Nov 27 12:00:01 lynx daemon.info noobia-sense: NOOBIA P1 battery level=94\n",
            encoding="utf-8"
        )

        reader = ViewReader("noobia-sense", backend="file", log_file=self.log_file)
        lines1 = reader.read_new()
        self.assertEqual(len(lines1), 2)

        # 2. Add an unread line to messages, then simulate BusyBox rotation:
        # messages -> messages.0, new messages created
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write("Nov 27 12:00:02 lynx daemon.info noobia-sense: NOOBIA P1 battery level=93\n")

        rotated = self.log_file.with_name("messages.0")
        self.log_file.rename(rotated)

        # New active messages file
        self.log_file.write_text(
            "Nov 27 12:00:03 lynx daemon.info noobia-sense: NOOBIA P1 battery level=92\n",
            encoding="utf-8"
        )

        # 3. Read new lines: should get level=93 from messages.0 AND level=92 from messages!
        lines2 = reader.read_new()
        self.assertEqual(len(lines2), 2)
        self.assertIn("level=93", lines2[0])
        self.assertIn("level=92", lines2[1])


if __name__ == "__main__":
    unittest.main()
