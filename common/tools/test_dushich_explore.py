import tempfile
import unittest
from pathlib import Path

import dushich_explore as explore


class ExploreTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        explore.ROOT = Path(self.folder.name)

    def tearDown(self):
        self.folder.cleanup()

    def test_rejects_bad_input(self):
        with self.assertRaises(ValueError):
            explore.start("  ", "Gwyn")
        with self.assertRaises(ValueError):
            explore.start("Where?", "; rm -rf /")
        with self.assertRaises(ValueError):
            explore.read_state("../etc")

    def test_report_lists_recorded_rows(self):
        text = explore.report({"id": "x", "status": "done", "commands": 3,
                               "answer": "It is in /noobia/council.",
                               "recorded": ["/noobia/council"]})
        self.assertIn("done, 3 commands", text)
        self.assertIn("Atlas rows written by Dushich (1): /noobia/council", text)
        self.assertIn("running", explore.report({"id": "x", "status": "running", "created": "t"}))

    def test_wait_returns_saved_state(self):
        job = "20261118T000000Z-0123abcd"
        (explore.ROOT / job).mkdir()
        explore.save_state(explore.ROOT / job, {"id": job, "status": "done", "answer": "ok"})
        self.assertEqual(explore.wait(job, 0)["answer"], "ok")


if __name__ == "__main__":
    unittest.main()
