"""Offline checks for Lynx's delayed optional-service startup."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import lynx_sensor_retry as retry


def state(action, audio=False, sensor=False):
    return {'action': action, 'reason': 'fixture',
            'audio_ready': audio, 'sensorhub_ready': sensor}


class RetryTest(unittest.TestCase):
    def test_probe_waits_at_22_percent_even_if_charging(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            snap = root / 'battery_snapshot'
            snap.write_text('gauge_device_type=42495\ncapacity_percent=22\n'
                            'temperature_millidegrees_celsius=25000\n'
                            'gauge_current_ma_signed=150\ncapacity_error=0\n'
                            'temperature_error=0\ncurrent_error=0\n')
            soc = root / 'soc'
            soc.mkdir()
            (soc / 'type').write_text('soc_max\n')
            (soc / 'temp').write_text('30000\n')
            class Result:
                returncode = 0
                stdout = json.dumps({'issues': []})
            with patch.object(retry, 'SNAPSHOT', snap), patch.object(retry, 'SOC', soc), \
                    patch.object(retry, 'interfaces', return_value=(False, False)), \
                    patch.object(retry, 'command', return_value=Result()):
                self.assertEqual(retry.probe()['action'], 'wait')

    def test_watch_starts_audio_then_sensorhub_only_after_gate(self):
        class Result:
            returncode = 0
        with patch.object(retry, 'probe', side_effect=[state('wait'),
                     state('attempt_start')]), patch.object(retry, 'interfaces',
                     return_value=(True, True)), patch.object(retry, 'command',
                     return_value=Result()) as command, patch.object(retry.time, 'sleep'), \
                patch.object(retry, 'idle_until_stopped') as idle:
            self.assertEqual(retry.watch(), 0)
            idle.assert_called_once_with()
            self.assertEqual([call.args[1:3] for call in command.call_args_list],
                             [('lynx-audio', 'start'), ('lynx-sensorhub', 'start')])

    def test_failed_start_stops_after_three_attempts(self):
        class Result:
            returncode = 1
        with patch.object(retry, 'probe', return_value=state('attempt_start')), \
                patch.object(retry, 'command', return_value=Result()) as command, \
                patch.object(retry.time, 'sleep'):
            self.assertEqual(retry.watch(), 1)
            self.assertEqual(command.call_count, 3)

    def test_already_ready_does_not_start_services(self):
        with patch.object(retry, 'probe', return_value=state('already_ready', True, True)), \
                patch.object(retry, 'command') as command, \
                patch.object(retry, 'idle_until_stopped') as idle:
            self.assertEqual(retry.watch(), 0)
            command.assert_not_called()
            idle.assert_called_once_with()


if __name__ == '__main__':
    unittest.main()
