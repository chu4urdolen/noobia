import json
import os
import tempfile
import textwrap
import unittest
from pathlib import Path

# Import the module under test
from projects.nexus_probe.summarize_reset_log import summarize_reset_log, _parse_line


class TestSummarizeResetLog(unittest.TestCase):
    def setUp(self) -> None:
        # Create a temporary JSONL file with a few records and one malformed line
        self.temp = tempfile.NamedTemporaryFile("w+", delete=False, encoding="utf-8")
        lines = [
            json.dumps({"boot_id": "bootA", "gpu": [50, 75.0, 20, 2048]}),
            json.dumps({"boot_id": "bootA", "gpu": [52, 80.0, 30, 2048]}),
            json.dumps({"boot_id": "bootB", "gpu": [48, 60.5, 15, 2048]}),
            "malformed line\n",
        ]
        self.temp.write("\n".join(lines))
        self.temp.flush()
        self.path = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.close()
        os.unlink(self.temp.name)

    def test_summary(self):
        summary = summarize_reset_log(self.path)
        self.assertEqual((summary["bootA"]["sample_count"], summary["bootA"]["peak_power"]), (2, 80.0))
        self.assertEqual((summary["bootB"]["sample_count"], summary["bootB"]["peak_power"]), (1, 60.5))

    def test_parse_line(self):
        # Valid line
        line = json.dumps({"boot_id": "X", "gpu": [0, 42.3, 0, 0]})
        self.assertEqual(_parse_line(line), ("X", 42.3))
        # Malformed JSON
        self.assertIsNone(_parse_line("{bad"))
        # Missing gpu list
        self.assertIsNone(_parse_line(json.dumps({"boot_id": "Y"})))
        # Wrong type
        self.assertIsNone(_parse_line(json.dumps({"boot_id": 1, "gpu": []})))

if __name__ == "__main__":
    unittest.main()

