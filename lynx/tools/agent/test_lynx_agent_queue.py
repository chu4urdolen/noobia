"""Security and crash boundaries for the Lynx agent job spool."""

import os
from pathlib import Path
import stat
import tempfile
import unittest

from lynx_agent_queue import JobQueue, QueueError


class QueueTest(unittest.TestCase):
    def test_submit_claim_finish_and_private_modes(self):
        with tempfile.TemporaryDirectory() as tmp:
            queue = JobQueue(Path(tmp) / "jobs")
            first = queue.create_job("one")
            second = queue.create_job("two")
            self.assertEqual(stat.S_IMODE(queue.root.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE((queue.root / (first + ".pending")).stat().st_mode), 0o600)
            self.assertEqual(queue.status(first), {"status": "pending"})
            self.assertEqual(queue.claim_next(), (first, "one"))
            self.assertEqual(JobQueue(queue.root).claim_next(), (second, "two"))
            self.assertIsNone(queue.claim_next())
            queue.finish(first, True, "completed")
            self.assertEqual(queue.status(first), {"status": "finished", "ok": True})
            self.assertEqual(stat.S_IMODE((queue.root / (first + ".done")).stat().st_mode), 0o600)

    def test_rejects_symlink_root_and_job(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "real"
            queue = JobQueue(target)
            (root / "link").symlink_to(target)
            with self.assertRaises(QueueError):
                JobQueue(root / "link")
            job_id = queue.create_job("private prompt")
            (queue.root / (job_id + ".pending")).unlink()
            (queue.root / (job_id + ".pending")).symlink_to(root / "outside")
            with self.assertRaises(QueueError):
                queue.claim_next()
            with self.assertRaises(QueueError):
                queue.status(job_id)
            with self.assertRaises(QueueError):
                queue.cancel(job_id)

    def test_cancel_and_bad_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            queue = JobQueue(Path(tmp) / "jobs")
            job_id = queue.create_job("cancel me")
            self.assertTrue(queue.cancel(job_id))
            self.assertFalse(queue.cancel(job_id))
            with self.assertRaises(QueueError):
                queue.status(job_id)
            with self.assertRaises(QueueError):
                queue.status("../../etc/passwd")
            with self.assertRaises(QueueError):
                queue.create_job("a" * 8001)

    def test_cancel_pending_sense_older_than_20s(self):
        with tempfile.TemporaryDirectory() as tmp:
            queue = JobQueue(Path(tmp) / "jobs")
            # Create a stale sense job (> 20s ago)
            stale_id = queue.create_job("[sense] Stale perception from long ago")
            stale_path = queue.root / (stale_id + ".pending")
            # Overwrite created_ns to 25 seconds ago
            import json, time
            with stale_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            data["created_ns"] = time.time_ns() - int(25 * 1e9)
            with stale_path.open("w", encoding="utf-8") as f:
                json.dump(data, f)

            # Create a fresh sense job (just created)
            fresh_id = queue.create_job("[sense] Fresh perception")

            # Create a regular user prompt created 25s ago (should NOT expire under max_sense_age_s)
            user_id = queue.create_job("user chat: hello")
            user_path = queue.root / (user_id + ".pending")
            with user_path.open("r", encoding="utf-8") as f:
                udata = json.load(f)
            udata["created_ns"] = time.time_ns() - int(25 * 1e9)
            with user_path.open("w", encoding="utf-8") as f:
                json.dump(udata, f)

            # claim_next with max_sense_age_s=20 should drop stale_id, and claim fresh_id (or user_id depending on order)
            # Both fresh_id and user_id should be claimed, but stale_id should be unlinked
            claimed = []
            while True:
                next_job = queue.claim_next(max_sense_age_s=20.0)
                if not next_job:
                    break
                claimed.append(next_job[0])

            self.assertNotIn(stale_id, claimed)
            self.assertIn(fresh_id, claimed)
            self.assertIn(user_id, claimed)
            self.assertFalse(stale_path.exists())


if __name__ == "__main__":
    unittest.main()
