"""Authenticated NRP/1's bounded adapter to the private Lynx agent queue."""

from pathlib import Path
import base64
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent / 'agent'))
from lynx_agent_queue import JobQueue
import lynx_noob_runtime as runtime


class AgentQueueNativeTest(unittest.TestCase):
    def test_submit_status_and_cancel_by_native_id(self):
        with tempfile.TemporaryDirectory() as directory:
            queue = JobQueue(Path(directory) / 'jobs')
            with patch.object(runtime, 'agent_job_queue', return_value=queue):
                node = runtime.Runtime()
                value, detail = node.registry.call(510, [], 'Reply ready')
                self.assertEqual(value, 1)
                job_id = detail.split('=', 1)[1]
                self.assertEqual(node.registry.call(511, [], job_id),
                                 (0, 'status=pending'))
                self.assertEqual(node.registry.call(512, [], job_id),
                                 (1, 'cancelled=1'))
                with self.assertRaises(runtime.NativeError):
                    node.registry.call(511, [], job_id)

    def test_common_abi_rejects_oversized_prompt(self):
        with tempfile.TemporaryDirectory() as directory:
            queue = JobQueue(Path(directory) / 'jobs')
            with patch.object(runtime, 'agent_job_queue', return_value=queue):
                node = runtime.Runtime()
                with self.assertRaises(runtime.NativeError):
                    node.registry.call('AGENT_SUBMIT', [], 'x' * 256)

    def test_result_chunks_reassemble_utf8_without_prompt(self):
        with tempfile.TemporaryDirectory() as directory:
            queue = JobQueue(Path(directory) / 'jobs')
            job_id = queue.create_job('private prompt')
            queue.claim_next()
            response = 'Lynx ✓ ' * 40
            queue.finish(job_id, True, response)
            with patch.object(runtime, 'agent_job_queue', return_value=queue):
                node = runtime.Runtime()
                self.assertEqual(node.registry.call(511, [], job_id),
                                 (2, 'status=finished ok=1'))
                assembled = bytearray()
                offset = 0
                while True:
                    total, detail = node.registry.call(513, [offset], job_id, mixed=True)
                    fields = dict(part.split('=', 1) for part in detail.split())
                    chunk = fields['data']
                    decoded = base64.urlsafe_b64decode(chunk + '=' * (-len(chunk) % 4))
                    assembled.extend(decoded)
                    offset += len(decoded)
                    self.assertEqual(total, len(response.encode()))
                    if fields['more'] == '0':
                        break
                self.assertEqual(assembled.decode(), response)
                self.assertNotIn('private prompt', detail)


if __name__ == '__main__':
    unittest.main()
