"""Offline contract tests for NRP AGENT_CANCEL (512) and lynx_codex cancellation.

These pin the behaviour cited in
lynx/linux-port/docs/LYNX-AGENT-CANCEL-20261121.md: AGENT_CANCEL removes only
*pending* queue jobs, and lynx_codex never enters that queue, so AGENT_CANCEL
cannot stop it. Nothing here contacts Lynx or touches a real queue.

Run: python3 -m unittest discover -s lynx/tools/agent -p 'test_agent_cancel_contract.py'
"""

import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

AGENT_DIR = Path(__file__).resolve().parent
TOOLS = AGENT_DIR.parent
sys.path.insert(0, str(AGENT_DIR))
sys.path.insert(0, str(TOOLS))

import lynx_noob_runtime as runtime  # noqa: E402
from lynx_agent_queue import JobQueue  # noqa: E402


class AgentCancelContract(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.jobs = Path(self.temp.name) / "jobs"
        self.patch = patch.object(runtime, "AGENT_JOBS", self.jobs)
        self.patch.start()
        self.queue = JobQueue(self.jobs)

    def tearDown(self):
        self.patch.stop()
        self.temp.cleanup()

    def cancel(self, text, numbers=()):
        return runtime.Runtime.agent_cancel(list(numbers), text)

    def test_pending_job_is_removed(self):
        job = self.queue.create_job("pending work")
        self.assertEqual(self.cancel(job), (1, "cancelled=1"))
        self.assertFalse(any(self.jobs.glob(job + ".*")))
        self.assertEqual(self.cancel(job), (0, "cancelled=0"))  # idempotent

    def test_missing_job_reports_zero(self):
        self.assertEqual(self.cancel("0" * 32), (0, "cancelled=0"))

    def test_running_job_is_not_stopped(self):
        job = self.queue.create_job("long work")
        self.assertEqual(self.queue.claim_next()[0], job)
        self.assertEqual(self.cancel(job), (0, "cancelled=0"))
        self.assertEqual(self.queue.status(job), {"status": "running"})

    def test_finished_job_is_untouched(self):
        job = self.queue.create_job("done work")
        self.queue.claim_next()
        self.queue.finish(job, True, "result")
        self.assertEqual(self.cancel(job), (0, "cancelled=0"))
        self.assertEqual(self.queue.status(job), {"status": "finished", "ok": True})

    def test_invalid_ids_are_rejected_without_touching_files(self):
        job = self.queue.create_job("keep me")
        for bad in ("", "../" + job, job.upper(), job + ".pending", "x" * 32):
            with self.subTest(bad=bad), self.assertRaises(runtime.NativeError) as ctx:
                self.cancel(bad)
            self.assertEqual(str(ctx.exception), "agent job unavailable")
        self.assertEqual(self.queue.status(job), {"status": "pending"})

    def test_numeric_arguments_are_rejected(self):
        with self.assertRaisesRegex(runtime.NativeError, "usage"):
            self.cancel("0" * 32, numbers=[1])

    def test_symlinked_pending_file_is_refused(self):
        target = Path(self.temp.name) / "elsewhere"
        target.write_text("{}")
        link = self.jobs / ("1" * 32 + ".pending")
        link.symlink_to(target)
        with self.assertRaises(runtime.NativeError):
            self.cancel("1" * 32)
        self.assertTrue(target.exists())


class CodexIsOutsideTheQueue(unittest.TestCase):
    """lynx_codex has no job ID, so AGENT_CANCEL cannot address it."""

    def test_codex_manifest_takes_no_job_id_and_has_no_nrp_id(self):
        spec = json.loads((TOOLS / "local_calls/lynx_codex.json").read_text())
        self.assertEqual(set(spec["inputSchema"]["properties"]), {"prompt", "model"})
        self.assertNotIn("nrp_id", spec)

    def test_codex_tool_runs_synchronously_without_the_queue(self):
        source = (AGENT_DIR / "lynx_codex_tool.py").read_text()
        self.assertNotIn("lynx_agent_queue", source)
        self.assertIn("process.communicate(timeout=120)", source)
        self.assertIn("os.killpg(process.pid, signal.SIGKILL)", source)
        wrapper = (TOOLS / "local_calls/lynx_codex.sh").read_text()
        self.assertIn("lynx-codex-tool", wrapper)


if __name__ == "__main__":
    unittest.main()
