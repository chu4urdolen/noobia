import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from argus_forge_feed import MAX_FEED_BYTES, parse_feed


def fixture():
    return {
        "paths": [{"path": "/noobia/argus", "project": "argus", "updated_by": "Aria",
                   "updated_at": "2026-11-26T20:00:00+00:00"}],
        "projects": [{"project_name": "argus", "modified_for": "Aria",
                      "last_modified": "2026-11-26T20:01:00+00:00"}],
        "notes": [{"id": 570, "project_name": "argus", "author": "Aria",
                   "created_at": "2026-11-26T22:02:00+02:00", "note": "A note"}],
    }


class ForgeFeedTest(unittest.TestCase):
    def test_stable_records_and_event_time(self):
        first = json.dumps(fixture()).encode()
        second = json.dumps(fixture(), sort_keys=True, indent=2).encode()
        first_hash, first_rows = parse_feed(first)
        second_hash, second_rows = parse_feed(second)
        self.assertNotEqual(first_hash, second_hash)
        self.assertEqual([r["stable_key"] for r in first_rows],
                         ["path:/noobia/argus", "project:argus", "note:570"])
        self.assertEqual([r["content_sha256"] for r in first_rows],
                         [r["content_sha256"] for r in second_rows])
        self.assertIsNone(first_rows[0]["occurred_at"])
        self.assertEqual(first_rows[0]["observed_at"], "2026-11-26T20:00:00+00:00")
        self.assertEqual(first_rows[2]["occurred_at"], "2026-11-26T20:02:00+00:00")

    def test_rejects_bad_shape_size_and_duplicate_source(self):
        with self.assertRaisesRegex(ValueError, "must contain"):
            parse_feed(b"{}")
        with self.assertRaisesRegex(ValueError, "5 MiB"):
            parse_feed(b"x" * (MAX_FEED_BYTES + 1))
        malformed = fixture()
        malformed["notes"].append(dict(malformed["notes"][0]))
        with self.assertRaisesRegex(ValueError, "duplicate Forge source ID"):
            parse_feed(json.dumps(malformed).encode())
        malformed = fixture()
        malformed["notes"][0]["created_at"] = "2026-11-26T20:02:00"
        with self.assertRaisesRegex(ValueError, "timezone"):
            parse_feed(json.dumps(malformed).encode())


if __name__ == "__main__":
    unittest.main()
