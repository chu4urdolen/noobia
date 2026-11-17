"""Race/order checks using fake SSH, fake scheduler, and fake relay only."""
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
from syra_power import Power


class PowerTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.directory = Path(self.folder.name)
        (self.directory / 'smartplug.json').write_text(json.dumps(
            {'backend': 'tuya', 'powers_syra': True, 'local_key': 'fake-test-only', 'device_id': 'fake'}))
        self.now = 1000
        self.events = []
        self.power = Power(self.directory, clock=lambda: self.now,
            command=lambda command: self.events.append(('command', command)),
            relay=lambda config, action: self.events.append(('relay', action)) or {'on': action == 'on'})

    def tearDown(self):
        self.folder.cleanup()

    def test_shutdown_verifies_relay_then_ssh_then_exact_five_minute_timer(self):
        state = self.power.shutdown()
        self.assertEqual(self.events[0], ('relay', 'status'))
        self.assertEqual(self.events[1][1][0], 'ssh')
        self.assertEqual(self.events[1][1][-1], 'sudo -n /usr/bin/systemctl poweroff')
        self.assertEqual(state['cut_at'], 1300)
        self.assertIn('--on-active=300s', self.events[2][1])

    def test_on_revokes_pending_cut_before_relay_and_stale_worker_cannot_cut(self):
        state = self.power.shutdown()
        self.events.clear()
        self.power.on()
        self.assertEqual(self.power.read()['status'], 'cancelled')
        self.assertEqual(self.events[-1], ('relay', 'on'))
        self.now = 1400
        self.assertEqual(self.power.cut(state['generation'])['status'], 'ignored')
        self.assertNotIn(('relay', 'off'), self.events)

    def test_repeated_shutdown_invalidates_first_timer(self):
        first = self.power.shutdown()
        second = self.power.shutdown()
        self.now = 1400
        self.assertNotEqual(first['generation'], second['generation'])
        self.assertEqual(self.power.cut(first['generation'])['status'], 'ignored')
        with patch('syra_power.subprocess.run', return_value=SimpleNamespace(returncode=1)):
            self.assertEqual(self.power.cut(second['generation'])['status'], 'completed')
        self.assertEqual(self.events[-1], ('relay', 'off'))

    def test_cannot_cut_early_or_cut_a_machine_back_online(self):
        state = self.power.shutdown()
        self.assertEqual(self.power.cut(state['generation'])['status'], 'ignored')
        self.now = 1300
        with patch('syra_power.subprocess.run', return_value=SimpleNamespace(returncode=0)):
            self.assertEqual(self.power.cut(state['generation'])['status'], 'cancelled')
        self.assertNotIn(('relay', 'off'), self.events)

    def test_missing_key_prevents_ssh_shutdown(self):
        (self.directory / 'smartplug.json').write_text(json.dumps(
            {'backend': 'tuya', 'powers_syra': True, 'device_id': 'fake', 'local_key': ''}))
        with self.assertRaisesRegex(RuntimeError, 'local key is missing'):
            self.power.shutdown()
        self.assertFalse(self.events)

    def test_concurrent_turn_on_and_timer_worker_cannot_reintroduce_a_cut(self):
        import threading
        state = self.power.shutdown()
        self.now = 1400
        entered = threading.Event()
        release = threading.Event()
        results = []
        original = self.power.relay
        def relay(config, action):
            if action == 'on':
                entered.set()
                self.assertTrue(release.wait(2))
            return original(config, action)
        self.power.relay = relay
        on = threading.Thread(target=self.power.on)
        on.start()
        self.assertTrue(entered.wait(2))
        worker = threading.Thread(target=lambda: results.append(self.power.cut(state['generation'])))
        worker.start()
        release.set()
        on.join(2)
        worker.join(2)
        self.assertFalse(on.is_alive())
        self.assertFalse(worker.is_alive())
        self.assertEqual(results[0]['status'], 'ignored')
        self.assertNotIn(('relay', 'off'), self.events)


if __name__ == '__main__':
    unittest.main()
