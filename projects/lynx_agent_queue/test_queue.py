import json
import os
import pathlib
import shutil
import tempfile
import unittest

from queue import JobQueue, JobError


class TestJobQueue(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.q = JobQueue(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _assert_file_mode(self, path, mode):
        self.assertEqual(oct(path.stat().st_mode & 0o777), oct(mode))

    def test_create_and_status(self):
        job_id = self.q.create_job("hello")
        status = self.q.status(job_id)
        self.assertEqual(status["status"], "pending")
        self._assert_file_mode(self.q._job_file(job_id), 0o600)

    def test_claim_order(self):
        ids = [self.q.create_job(str(i)) for i in range(3)]
        # Claim should return the earliest created job
        claimed = self.q.claim_next()
        self.assertEqual(claimed, ids[0])
        status = self.q.status(claimed)
        self.assertEqual(status["status"], "claimed")
        # Next claim returns second
        self.assertEqual(self.q.claim_next(), ids[1])

    def test_duplicate_claim(self):
        job_id = self.q.create_job("dup")
        first = self.q.claim_next()
        self.assertEqual(first, job_id)
        # Second claim should skip the claimed job
        self.assertIsNone(self.q.claim_next())

    def test_finish_and_result(self):
        job_id = self.q.create_job("work")
        self.q.claim_next()
        self.q.finish(job_id, True, "done")
        status = self.q.status(job_id)
        self.assertEqual(status["status"], "finished")
        self.assertTrue(status["ok"])
        self.assertEqual(status["text"], "done")
        self._assert_file_mode(self.q._job_file(job_id, "done"), 0o600)

    def test_cancel(self):
        job_id = self.q.create_job("cancel")
        self.q.cancel(job_id)
        with self.assertRaises(JobError):
            self.q.status(job_id)

    def test_malformed_id(self):
        with self.assertRaises(JobError):
            self.q.status("badid")

    def test_prompt_length(self):
        with self.assertRaises(JobError):
            self.q.create_job("")
        with self.assertRaises(JobError):
            self.q.create_job("a" * 8001)

