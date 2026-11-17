"""Offline integration of Lynx's private queue with its one-shot worker."""

from pathlib import Path
import multiprocessing
import os
import signal
import tempfile
import time
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from lynx_agent_queue import JobQueue
import lynx_agent_worker as worker


def run_stoppable_job(queue_root, agent, job):
    """Run the real worker handler in an isolated test process."""
    signal.signal(signal.SIGTERM, worker.stop)
    with patch.object(worker, 'AGENT', str(agent)):
        worker.run_job(JobQueue(queue_root), job[0], job[1])


class WorkerTest(unittest.TestCase):
    def test_missing_agent_executable_finishes_job_without_crashing(self):
        with tempfile.TemporaryDirectory() as directory:
            queue = JobQueue(Path(directory) / 'jobs')
            job_id = queue.create_job('safe prompt')
            with patch.object(worker.subprocess, 'Popen',
                              side_effect=FileNotFoundError):
                worker.run_job(queue, *queue.claim_next())
            self.assertEqual(queue.status(job_id),
                             {'status': 'finished', 'ok': False})
            self.assertIn('Agent executable unavailable',
                          (queue.root / (job_id + '.done')).read_text())

    def test_inference_gate_waits_for_nexus_without_cloud_key(self):
        with patch.object(worker.urllib.request, 'urlopen',
                          side_effect=URLError('offline')), \
             patch.object(worker, 'key_from', side_effect=FileNotFoundError):
            self.assertFalse(worker.inference_ready())

    def test_inference_gate_does_not_fallback_on_nexus_error(self):
        with patch.object(worker.urllib.request, 'urlopen',
                          side_effect=HTTPError(worker.LOCAL, 503, 'unavailable', {}, None)), \
             patch.object(worker, 'key_from') as key:
            self.assertFalse(worker.inference_ready())
            key.assert_not_called()

    def test_prompt_is_piped_to_child_and_result_is_private(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            agent = root / 'fake_agent.py'
            agent.write_text('import sys\nassert sys.argv == [sys.argv[0], "--stdin"]\n'
                             'assert sys.stdin.read() == "private prompt"\n'
                             'print("agent ready")\n')
            queue = JobQueue(root / 'jobs')
            job_id = queue.create_job('private prompt')
            claim = queue.claim_next()
            self.assertEqual(claim[0], job_id)
            with patch.object(worker, 'AGENT', str(agent)):
                worker.run_job(queue, *claim)
            self.assertEqual(queue.status(job_id), {'status': 'finished', 'ok': True})
            self.assertEqual((queue.root / (job_id + '.done')).stat().st_mode & 0o777, 0o600)
            self.assertIn('agent ready', (queue.root / (job_id + '.done')).read_text())

    def test_stop_interrupts_running_child_and_records_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            child_pid = root / 'child.pid'
            agent = root / 'slow_agent.py'
            agent.write_text('import os, pathlib, time\n'
                             f'pathlib.Path({str(child_pid)!r}).write_text(str(os.getpid()))\n'
                             'time.sleep(30)\n')
            queue = JobQueue(root / 'jobs')
            job_id = queue.create_job('stop this fake task')
            job = queue.claim_next()
            process = multiprocessing.get_context('fork').Process(
                target=run_stoppable_job, args=(queue.root, agent, job))
            process.start()
            try:
                deadline = time.monotonic() + 5
                while not child_pid.exists() and time.monotonic() < deadline:
                    time.sleep(0.02)
                self.assertTrue(child_pid.exists(), 'fake agent did not start')
                os.kill(process.pid, signal.SIGTERM)
                process.join(5)
                self.assertFalse(process.is_alive(), 'worker did not stop promptly')
                self.assertEqual(process.exitcode, 0)
                self.assertEqual(queue.status(job_id),
                                 {'status': 'finished', 'ok': False})
                self.assertIn('Agent stopped',
                              (queue.root / (job_id + '.done')).read_text())
                with self.assertRaises(ProcessLookupError):
                    os.kill(int(child_pid.read_text()), 0)
            finally:
                if process.is_alive():
                    process.kill()
                    process.join(2)


if __name__ == '__main__':
    unittest.main()
