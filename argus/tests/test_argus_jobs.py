from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from argus_jobs import (claim_next, connect, enqueue, health, job_status,
                        recover_interrupted, run_once, worker_lock)


class JobsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / "private/jobs.sqlite3"

    def test_idempotent_request_and_durable_result(self):
        connection = connect(self.db)
        first = enqueue(connection, "archive-import", "archive:2026-11-26")
        repeated = enqueue(connection, "archive-import", "archive:2026-11-26")
        self.assertEqual(first["job_id"], repeated["job_id"])
        self.assertTrue(repeated["reused"])
        with worker_lock(self.db):
            result = run_once(connection, lambda kind, date: {"kind": kind, "date": date,
                                                              "records_added": 0})
        self.assertEqual(result["state"], "done")
        self.assertEqual(health(connection)["done"], 1)
        connection.close()
        with connect(self.db) as reopened:
            self.assertEqual(job_status(reopened, first["job_id"], True)["result"],
                             {"kind": "archive-import", "date": None, "records_added": 0})
            self.assertFalse(run_once(reopened)["claimed"])

    def test_only_one_running_and_interrupted_is_not_replayed(self):
        with connect(self.db) as connection:
            first = enqueue(connection, "archive-import")
            second = enqueue(connection, "archive-import")
            claimed = claim_next(connection)
            self.assertIsNotNone(claimed)
            self.assertIsNone(claim_next(connection))
            self.assertEqual(recover_interrupted(connection), 1)
            self.assertEqual(job_status(connection, claimed[0], True)["state"], "failed")
            next_job = claim_next(connection)
            self.assertEqual(next_job[0], second["job_id"] if claimed[0] == first["job_id"]
                             else first["job_id"])

    def test_worker_lock_and_validation(self):
        with connect(self.db) as connection:
            with self.assertRaisesRegex(ValueError, "unsupported job kind"):
                enqueue(connection, "shell")
            with self.assertRaisesRegex(ValueError, "request key"):
                enqueue(connection, "archive-import", "bad key")
            with self.assertRaisesRegex(ValueError, "requires --date"):
                enqueue(connection, "ledger-day")
            with self.assertRaisesRegex(ValueError, "does not accept a date"):
                enqueue(connection, "archive-import", target_date="2026-11-26")
            with self.assertRaisesRegex(ValueError, "invalid job ID"):
                job_status(connection, "../../secrets")
        with worker_lock(self.db):
            with self.assertRaisesRegex(ValueError, "another Argus worker"):
                with worker_lock(self.db):
                    pass

    def test_ledger_job_and_v1_migration(self):
        self.db.parent.mkdir(parents=True)
        with sqlite3.connect(self.db) as old:
            old.execute("CREATE TABLE jobs(job_id TEXT PRIMARY KEY,kind TEXT NOT NULL,"
                        "request_key TEXT UNIQUE,state TEXT NOT NULL,created_at TEXT NOT NULL,"
                        "started_at TEXT,finished_at TEXT,result_json TEXT,error TEXT)")
            old.execute("PRAGMA user_version=1")
        with connect(self.db) as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 2)
            queued = enqueue(connection, "ledger-day", "ledger:2026-11-26", "2026-11-26")
            result = run_once(connection, lambda kind, date: {"kind": kind, "date": date})
            self.assertEqual(result["state"], "done")
            self.assertEqual(job_status(connection, queued["job_id"], True)["target_date"],
                             "2026-11-26")


if __name__ == "__main__":
    unittest.main()
