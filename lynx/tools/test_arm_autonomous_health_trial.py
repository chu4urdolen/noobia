"""Offline sequencing checks for the detached pinned-listener trial window."""
import json
import os
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import arm_autonomous_health_trial as arm


def main():
    os.umask(0o077)
    with tempfile.TemporaryDirectory(prefix='autonomous-window-fixture-', dir=arm.ROOT / 'logs') as temp:
        out = Path(temp)
        receipt = out / 'contact.json'
        receipt.write_text(json.dumps({'state': 'native-ssh-available', 'native_ssh_verified': True}))
        arm.save(out / 'result.json', {'state': 'starting', 'usb_unplugged_confirmed': True})
        calls = []

        class FakeListener:
            def __init__(self, command, **kwargs):
                calls.append(('listener', Path(command[1]).name))
                kwargs['stdout'].write(('LISTENER READY: ' + str(receipt) + '\n').encode())
                kwargs['stdout'].flush()
                self.pid = 12345

            def poll(self):
                return None

            def wait(self, timeout):
                return 0

            def terminate(self):
                raise AssertionError('Successful listener should not be terminated')

        def fake_run(command, **kwargs):
            name = Path(command[1]).name
            calls.append(('run', name))
            if name == 'launch_autonomous_health_ram_trial.py':
                kwargs['stdout'].write((json.dumps({'result': str(out / 'trial.json')}) + '\n').encode())
            elif name == 'collect_battery_session.py':
                kwargs['stdout'].write((json.dumps({'result': str(out / 'logger.json')}) + '\n').encode())
            else:
                raise AssertionError('Unexpected worker command: ' + name)
            kwargs['stdout'].flush()
            return SimpleNamespace(returncode=0)

        with patch.object(arm.subprocess, 'Popen', FakeListener), \
                patch.object(arm.subprocess, 'run', fake_run):
            arm.worker(out)
        result = json.loads((out / 'result.json').read_text())
        if (result['state'] != 'ram-health-trial-complete' or
                result.get('trial_receipt') != str(out / 'trial.json') or
                result.get('host_logger_receipt') != str(out / 'logger.json') or
                calls != [('listener', 'lynx_wifi_v19_contact.py'),
                          ('run', 'launch_autonomous_health_ram_trial.py'),
                          ('run', 'collect_battery_session.py')]):
            raise AssertionError('Listener, trial and logger did not run in order')
        arm.save(out / 'result.json', {'state': 'starting', 'usb_unplugged_confirmed': False})
        try:
            arm.worker(out)
        except ValueError:
            pass
        else:
            raise AssertionError('Worker accepted missing USB precondition')
    report = {'passed': True, 'checks': ['listener ready before trial',
                                        'trial before logger',
                                        'missing unplugged confirmation refused'],
              'phone_contacted': False, 'flash_performed': False}
    destination = arm.ROOT / 'linux-port/artifacts' / ('autonomous-window-check-' + str(time.time_ns()))
    destination.mkdir(mode=0o700)
    (destination / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'passed': True, 'result': str(destination / 'result.json')}))


if __name__ == '__main__':
    main()
