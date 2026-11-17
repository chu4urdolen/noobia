import asyncio
import os
import signal
import sys
import unittest
from capture_supervisor import Capture


class RecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_child_exit_restarts_without_losing_subscribers(self):
        events = []
        children = []
        async def factory():
            code = 'import json,time; print(json.dumps({"type":"audio","level":0.1}),flush=True); '
            code += 'raise SystemExit(3)' if not children else 'time.sleep(60)'
            child = await asyncio.create_subprocess_exec(sys.executable, '-c', code,
                stdout=asyncio.subprocess.PIPE, start_new_session=True)
            children.append(child)
            return child
        capture = Capture(factory, events.append, retry_seconds=.01)
        capture.start()
        try:
            async with asyncio.timeout(3):
                while len(children) < 2 or sum(e.get('type') == 'audio' for e in events) < 2:
                    await asyncio.sleep(.01)
            self.assertIn('retrying', [e.get('phase') for e in events])
            os.killpg(children[-1].pid, signal.SIGTERM)
            async with asyncio.timeout(3):
                while len(children) < 3:
                    await asyncio.sleep(.01)
        finally:
            await capture.stop()
        self.assertTrue(all(child.returncode is not None for child in children))
        count = len(children)
        await asyncio.sleep(.05)
        self.assertEqual(len(children), count)

    async def test_spawn_failure_recovers_with_bounded_retry(self):
        attempts = 0
        events = []
        async def factory():
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise FileNotFoundError('USB missing')
            return await asyncio.create_subprocess_exec(sys.executable, '-c',
                'import time; print(\'{"type":"audio"}\',flush=True); time.sleep(60)',
                stdout=asyncio.subprocess.PIPE, start_new_session=True)
        capture = Capture(factory, events.append, retry_seconds=.01)
        capture.start()
        try:
            async with asyncio.timeout(3):
                while not any(e.get('type') == 'audio' for e in events):
                    await asyncio.sleep(.01)
            self.assertEqual(attempts, 2)
        finally:
            await capture.stop()


if __name__ == '__main__':
    unittest.main()
