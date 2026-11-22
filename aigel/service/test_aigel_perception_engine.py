"""Unit tests for Aigel Perception Engine and DB Tools."""

from pathlib import Path
import tempfile
import unittest

import sys
_AUTONOMY = Path(__file__).resolve().parents[2] / "common" / "autonomy"
if str(_AUTONOMY) not in sys.path:
    sys.path.insert(0, str(_AUTONOMY))
_SERVICE = Path(__file__).resolve().parent
if str(_SERVICE) not in sys.path:
    sys.path.insert(0, str(_SERVICE))

from aigel_perception_engine import AigelPerceptionEngine, LogSource
from pattern_db import PatternDB


class TestAigelPerceptionEngine(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_dir = Path(self.tmp.name)
        self.db_path = self.tmp_dir / "test_patterns.db"
        self.log_path = self.tmp_dir / "test_sensory.log"
        self.db = PatternDB(self.db_path, seed_defaults=False)
        self.source = LogSource(f"file:{self.log_path}")
        self.engine = AigelPerceptionEngine(
            source=self.source,
            host="lynx-test",
            db=self.db,
            review_interval_s=600,
            use_llm=False,  # Use deterministic heuristic for fast unit testing
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_learn_noisy_line_as_ignore(self):
        # Emit a noisy tick
        self.log_path.write_text("[sensorhub] sync_poll_tick seq=5432 status=ok latency=0.2ms\n")
        res = self.engine.step()

        self.assertEqual(res["processed_count"], 1)
        r = res["results"][0][1]
        self.assertEqual(r["status"], "learned_new_pattern")
        pat = r["pattern"]
        self.assertTrue(pat["ignore"], "Noisy line should be set to ignore=True")
        self.assertFalse(pat["to_noob"], "Noisy line should not be sent to Noob")
        self.assertIsNone(pat["message"])

        # Second occurrence: should match without re-learning
        with open(self.log_path, "a") as f:
            f.write("[sensorhub] sync_poll_tick seq=5433 status=ok latency=0.3ms\n")
        res2 = self.engine.step()
        self.assertEqual(res2["processed_count"], 1)
        r2 = res2["results"][0][1]
        self.assertEqual(r2["status"], "matched_ignore", "Second occurrence must match the ignore pattern")

    def test_learn_meaningful_perception(self):
        # Emit a novel physical event
        self.log_path.write_text("NOOBIA P1 sensory proximity.approach distance=12cm entity=hand\n")
        res = self.engine.step()

        self.assertEqual(res["processed_count"], 1)
        r = res["results"][0][1]
        self.assertEqual(r["status"], "learned_new_pattern")
        pat = r["pattern"]
        self.assertFalse(pat["ignore"])
        self.assertTrue(pat["to_noob"])
        self.assertIsNotNone(pat["message"])
        self.assertIn("perceive", r["message"].lower())

        # Second occurrence matches as perception
        with open(self.log_path, "a") as f:
            f.write("NOOBIA P1 sensory proximity.approach distance=10cm entity=hand\n")
        res2 = self.engine.step()
        self.assertEqual(res2["processed_count"], 1)
        r2 = res2["results"][0][1]
        self.assertEqual(r2["status"], "matched_perception")

    def test_diagnostic_review(self):
        # Emit anomaly line
        self.log_path.write_text("[touch] buffer_warning dropped_events=55 queue_overflow=1\n")
        self.engine.step()

        suggestions = self.engine.run_10min_diagnostic_review()
        self.assertTrue(len(suggestions) > 0)
        self.assertTrue(any("drop" in s.lower() for s in suggestions))


if __name__ == "__main__":
    unittest.main()
