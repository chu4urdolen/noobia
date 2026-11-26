import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from argus_history import (capture_journal, connect, events_on, find_events,
                           import_archive, journal_day, status)


def event(event_id, date, summary):
    return {
        "schema_version": 1,
        "event_id": event_id,
        "event_date": date,
        "recorded_at": "2026-08-23T17:00:00Z",
        "type": "milestone",
        "title": "A record",
        "summary": summary,
        "participants": ["Argus"],
    }


class HistoryTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.archive = self.root / "archive"
        self.events = self.archive / "events/2026"
        self.events.mkdir(parents=True)
        self.source = self.events / "2026-08-23.jsonl"
        self.db = self.root / "history.sqlite3"

    def write(self, *records):
        data = "".join(json.dumps(x) + "\n" for x in records).encode()
        self.source.write_bytes(data)
        return data

    def test_import_retains_bytes_versions_and_uncertain_dates(self):
        original = self.write(event("A-1", "2026-08-23", "First account"),
                              event("A-2", None, "Date unknown"))
        with connect(self.db) as connection:
            self.assertEqual(import_archive(connection, self.archive),
                             {"files_seen": 1, "snapshots_added": 1, "records_added": 2})
            self.assertEqual(import_archive(connection, self.archive)["records_added"], 0)
            self.assertEqual(len(events_on(connection, "2026-08-23", 100)), 1)
            self.assertEqual(events_on(connection, "2026-08-23", 100)[0]["source_line"], 1)
            self.assertEqual(connection.execute(
                "SELECT raw_bytes FROM file_snapshots ORDER BY snapshot_id LIMIT 1"
            ).fetchone()[0], original)

            revised = self.write(event("A-1", "2026-08-23", "Corrected account"),
                                 event("A-2", None, "Date unknown"))
            self.assertEqual(import_archive(connection, self.archive),
                             {"files_seen": 1, "snapshots_added": 1, "records_added": 1})
            self.assertEqual(status(connection)["snapshots"], 2)
            self.assertEqual(status(connection)["raw_records"], 3)
            self.assertEqual(connection.execute(
                "SELECT raw_bytes FROM file_snapshots ORDER BY snapshot_id DESC LIMIT 1"
            ).fetchone()[0], revised)
            self.assertEqual({x["summary"] for x in events_on(connection, "2026-08-23", 100)},
                             {"First account", "Corrected account"})
            self.assertEqual(len(find_events(connection, "Argus", 100)), 3)
            self.assertEqual(find_events(connection, "A-1", 100)[0]["event_id"], "A-1")

    def test_bad_file_does_not_partially_import(self):
        self.source.write_text(json.dumps(event("A-1", "2026-08-23", "Valid")) + "\n{" )
        with connect(self.db) as connection:
            with self.assertRaisesRegex(ValueError, "2026-08-23.jsonl:2"):
                import_archive(connection, self.archive)
            self.assertEqual(status(connection)["snapshots"], 0)
            self.assertEqual(status(connection)["raw_records"], 0)

    def test_symlink_outside_archive_rejected(self):
        outside = self.root / "outside.jsonl"
        outside.write_text(json.dumps(event("A-1", "2026-08-23", "Outside")))
        self.source.symlink_to(outside)
        with connect(self.db) as connection:
            with self.assertRaisesRegex(ValueError, "unsafe archive path"):
                import_archive(connection, self.archive)

    def test_journal_capture_versions_latest_day_and_migration(self):
        with connect(self.db) as connection:
            connection.execute("PRAGMA user_version=1")
        old = b"# Aria's journal\n\n## 2026-11-22 \xe2\x80\x94 First account\nThe earlier text.\n"
        new = b"# Aria's journal\n\n## 2026-11-22 \xe2\x80\x94 Revised account\nThe later text.\n"
        with connect(self.db) as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 2)
            self.assertEqual(capture_journal(connection, "aria", old)["snapshot_added"], 1)
            self.assertEqual(capture_journal(connection, "aria", old)["snapshot_added"], 0)
            self.assertEqual(capture_journal(connection, "aria", new)["snapshot_added"], 1)
            self.assertEqual(status(connection)["journal_snapshots"], 2)
            self.assertEqual(connection.execute(
                "SELECT raw_bytes FROM journal_snapshots ORDER BY snapshot_id LIMIT 1"
            ).fetchone()[0], old)
            rows = journal_day(connection, "2026-11-22", 10)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["heading"], "2026-11-22 — Revised account")
            self.assertEqual(rows[0]["source_line"], 3)
            with self.assertRaisesRegex(ValueError, "unregistered journal"):
                capture_journal(connection, "unknown", old)
            self.assertEqual(status(connection)["journal_sources"], 1)


if __name__ == "__main__":
    unittest.main()
