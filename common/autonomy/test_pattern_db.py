"""Unit tests for SQLite PatternDB (host primary index, output_message secondary index)."""

from pathlib import Path
import tempfile
import unittest

from pattern_db import PatternDB


class TestPatternDB(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "patterns.db"
        self.db = PatternDB(self.db_path)

    def tearDown(self):
        self.tmp.cleanup()

    def test_upsert_and_retrieve_top_patterns(self):
        pat1 = {
            "id": "cat-seen",
            "match": {"sense": "camera", "event": "object.seen", "fields": {"label": "cat"}},
            "message": "A cat appeared in front of you",
            "to_noob": True,
            "cooldown_s": 300,
            "examples": {
                "must": ["NOOBIA P1 camera object.seen label=cat conf=0.9"],
                "must_not": ["NOOBIA P1 camera object.seen label=dog conf=0.9"],
            },
        }
        pat2 = {
            "id": "laptop-seen",
            "match": {"sense": "camera", "event": "object.seen", "fields": {"label": "laptop"}},
            "message": "You see a laptop",
            "to_noob": True,
            "cooldown_s": 120,
            "examples": {
                "must": ["NOOBIA P1 camera object.seen label=laptop conf=0.76"],
                "must_not": ["NOOBIA P1 camera object.seen label=cup conf=0.5"],
            },
        }

        self.assertTrue(self.db.upsert_pattern(pat1, host="lynx"))
        self.assertTrue(self.db.upsert_pattern(pat2, host="lynx"))
        self.assertEqual(self.db.count_patterns("lynx"), 2)

        # Record hits on laptop
        self.db.record_hit("laptop-seen")
        self.db.record_hit("laptop-seen")

        top = self.db.get_top_ranker_patterns("lynx", limit=100)
        self.assertEqual(len(top), 2)
        # cat-seen was upserted once with initial_count=1 -> count=1
        # laptop-seen was upserted once (count=1), then record_hit twice -> count=3
        self.assertEqual(top[0]["id"], "laptop-seen")
        self.assertEqual(top[0]["hits"], 3)
        self.assertEqual(top[0]["message"], "You see a laptop")
        self.assertEqual(top[1]["id"], "cat-seen")
        self.assertEqual(top[1]["hits"], 1)

        # Dynamic ranker selection with require_hits=True
        active_ranker = self.db.get_top_ranker_patterns("lynx", limit=100, require_hits=True)
        self.assertEqual(len(active_ranker), 2)

    def test_host_isolation(self):
        pat = {
            "id": "net-device",
            "match": {"sense": "network", "event": "device.seen"},
            "message": "A network device was detected",
        }
        self.db.upsert_pattern(pat, host="nexus")
        self.assertEqual(self.db.count_patterns("lynx"), 0)
        self.assertEqual(self.db.count_patterns("nexus"), 1)


if __name__ == "__main__":
    unittest.main()
