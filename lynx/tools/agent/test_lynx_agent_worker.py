"""Offline integration of Lynx's private queue with its one‑shot worker.

This file lives in the Dushich workspace and mirrors the original test in
the shared repository.  The original test exercised the worker's ability to
pipe a prompt to the child agent and verify that the job result was written
to a private ``.done`` file.  For the current assignment we add a second
test that verifies the worker correctly handles a ``SIGTERM`` sent while a
job is in flight.  The worker's signal handler should terminate the child
process group and mark the job finished with ``ok=False``.

The implementation uses a lightweight fake agent that simply sleeps for a
few seconds.  The test sends ``SIGTERM`` to the test process, which the
worker's ``stop`` handler intercepts and propagates to the child.  After the
worker exits we assert that the job status is ``finished`` with ``ok`` set
to ``False`` and that the result file contains the expected "Agent stopped"
text.
"""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import os
import signal
import threading
import time

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from lynx_agent_queue import JobQueue
import lynx_agent_worker as worker


class WorkerTest(unittest.TestCase):
    def test_prompt_is_piped_to_child_and_result_is_private(self):
        """Verify that a prompt is piped to the child and the result is
        written to a private ``.done`` file.
        """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            agent = root / "fake_agent.py"
            agent.write_text(
                """import sys
assert sys.argv == [sys.argv[0], "--stdin"]
assert sys.stdin.read() == "private prompt"
print("agent ready")
"""
            )
            queue = JobQueue(root / "jobs")
            job_id = queue.create_job("private prompt")
            claim = queue.claim_next()
            self.assertEqual(claim[0], job_id)
            with patch.object(worker, "AGENT", str(agent)):
                worker.run_job(queue, *claim)
            self.assertEqual(queue.status(job_id), {"status": "finished", "ok": True})
            self.assertEqual((queue.root / (job_id + ".done")).stat().st_mode & 0o777, 0o600)
            self.assertIn("agent ready", (queue.root / (job_id + ".done")).read_text())

    def test_worker_stops_child_on_sigterm_and_finishes_with_ok_false(self):
        """Verify that a SIGTERM sent while a job is running terminates the
        child process group and marks the job as finished with ``ok=False``.
        """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            agent = root / "fake_agent.py"
            # Fake agent that sleeps; it ignores stdin.
            agent.write_text(
                """import sys, time
assert sys.argv[1] == "--stdin"
time.sleep(5)
print("finished")
"""
            )
            queue = JobQueue(root / "jobs")
            job_id = queue.create_job("dummy prompt")
            claim = queue.claim_next()
            self.assertEqual(claim[0], job_id)
            with patch.object(worker, "AGENT", str(agent)):
                # Install the SIGTERM handler that the worker expects.
                signal.signal(signal.SIGTERM, worker.stop)
                # Run the worker in a separate thread so we can send SIGTERM.
                def run():
                    worker.run_job(queue, *claim)

                t = threading.Thread(target=run, daemon=True)
                t.start()
                # Allow the child to start.
                time.sleep(0.1)
                os.kill(os.getpid(), signal.SIGTERM)
                t.join()
            status = queue.status(job_id)
            self.assertEqual(status, {"status": "finished", "ok": False})
            done_path = queue.root / f"{job_id}.done"
            self.assertEqual(done_path.stat().st_mode & 0o777, 0o600)
            text = done_path.read_text()
            self.assertIn("Agent stopped", text)


if __name__ == "__main__":
    unittest.main()

