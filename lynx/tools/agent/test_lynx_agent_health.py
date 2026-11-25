"""Privacy and progress checks for Lynx's read-only queue summary."""

import os
from pathlib import Path
import tempfile
import unittest

from lynx_agent_health import snapshot


class HealthTest(unittest.TestCase):
    def test_private_queue_counts_without_contents(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'jobs'
            root.mkdir(mode=0o700)
            pending = root / ('a' * 32 + '.pending')
            pending.write_text('SECRET PROMPT')
            pending.chmod(0o600)
            os.utime(pending, (100, 100))
            done = root / ('b' * 32 + '.done')
            done.write_text('SECRET RESULT')
            done.chmod(0o600)
            state = snapshot(root, Path(directory) / 'stop', now=130)
            self.assertEqual(state['counts'], {'pending': 1, 'running': 0, 'done': 1})
            self.assertEqual(state['oldest_pending_seconds'], 30)
            self.assertEqual(state['issues'], [])
            self.assertNotIn('SECRET', str(state))
            self.assertNotIn('a' * 32, str(state))

    def test_symlink_and_writable_file_are_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'jobs'
            root.mkdir(mode=0o700)
            (root / ('a' * 32 + '.pending')).symlink_to('/etc/passwd')
            done = root / ('b' * 32 + '.done')
            done.write_text('x')
            done.chmod(0o666)
            state = snapshot(root, Path(directory) / 'stop')
            self.assertIn('entry_not_private', state['issues'])
            self.assertEqual(state['counts']['pending'], 0)

    def test_stop_marker_is_reported_without_becoming_an_issue(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'jobs'
            root.mkdir(mode=0o700)
            stop = Path(directory) / 'stop'
            stop.write_text('')
            stop.chmod(0o600)
            state = snapshot(root, stop)
            self.assertTrue(state['stopped'])
            self.assertEqual(state['issues'], [])


if __name__ == '__main__':
    unittest.main()
