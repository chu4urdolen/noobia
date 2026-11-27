"""Unit tests for AsyncJobManager and ActionLock (NA-20)."""

import tempfile
import time
import unittest
from pathlib import Path
from common.autonomy.asyncjob import ActionLock, AsyncJobManager


class TestAsyncJob(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.lock_dir = Path(self.temp_dir.name)
        self.emitted = []
        self.manager = AsyncJobManager(lock_dir=self.lock_dir, emitter=self.emitted.append)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_lock_exclusivity(self):
        lock1 = ActionLock("net_test", lock_dir=self.lock_dir)
        lock2 = ActionLock("net_test", lock_dir=self.lock_dir)

        self.assertTrue(lock1.acquire())
        self.assertFalse(lock2.acquire())
        lock1.release()
        self.assertTrue(lock2.acquire())
        lock2.release()

    def test_run_async_success(self):
        def sample_work(x, y):
            time.sleep(0.05)
            return {"sentence": f"Result is {x + y}"}

        res = self.manager.run_async("calc", "add", sample_work, args=(3, 4))
        self.assertTrue(res["ok"])
        self.assertIn("job_id", res)

        # While running, a second call with same tool and action should be busy
        res2 = self.manager.run_async("calc", "add", sample_work, args=(1, 1))
        self.assertFalse(res2["ok"])
        self.assertTrue(res2["busy"])

        # Wait for thread to finish
        time.sleep(0.1)

        # Verify emitted lifecycle events
        self.assertEqual(len(self.emitted), 2)
        self.assertIn("job.started", self.emitted[0])
        self.assertIn("job.done", self.emitted[1])
        self.assertIn("Result is 7", self.emitted[1])

    def test_run_async_failure_emits_failed_event(self):
        def fail_work():
            time.sleep(0.02)
            raise RuntimeError("network down")

        res = self.manager.run_async("probe", "ping", fail_work)
        self.assertTrue(res["ok"])

        time.sleep(0.08)

        self.assertEqual(len(self.emitted), 2)
        self.assertIn("job.started", self.emitted[0])
        self.assertIn("job.failed", self.emitted[1])
        self.assertIn("RuntimeError: network down", self.emitted[1])


if __name__ == "__main__":
    unittest.main()
