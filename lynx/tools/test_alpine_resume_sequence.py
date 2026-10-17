"""Offline control-flow tests for optional Alpine resume; no real subprocesses."""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import resume_battery_session as resume
from configure_alpine_runtime import load_stage


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage-receipt', type=Path, required=True)
    args = parser.parse_args()
    stage = args.stage_receipt.resolve(strict=True)
    load_stage(stage)
    os.umask(0o077)
    out = resume.ROOT / 'linux-port/artifacts' / ('alpine-resume-sequence-' + str(time.time_ns()))
    out.mkdir(mode=0o700)
    checks = {}
    for case in ['without-alpine', 'alpine-success', 'alpine-failure', 'clock-failure']:
        root = out / case
        port = root / 'linux-port'
        worker = root / 'worker'
        worker.mkdir(parents=True)
        watch = b'fixture battery watcher\n'
        port.mkdir()
        (port / 'battery-watch.sh').write_bytes(watch)
        test = port / 'artifacts/battery-watch-check-fixture'
        test.mkdir(parents=True)
        (test / 'result.json').write_text(json.dumps({'passed': True, 'source_sha256': hashlib.sha256(watch).hexdigest()}))
        session = root / 'session.json'
        session.write_text(json.dumps({'finished_ns': 1, 'session_left_running': True, 'extra_diagnostic': {'exit_code': 0}}))
        monitor = root / 'monitor'
        monitor.mkdir()
        (monitor / 'load-and-snapshot.stdout').write_text('temperature_error=0\nvoltage_error=0\ncurrent_error=0\ncapacity_error=0\n')
        calls = []
        logger_started = []

        def fake_run(argv, **kwargs):
            name = Path(argv[1]).name
            calls.append(name)
            rc = 0
            responses = {
                'start_gauge_listener.py': {'ready_verified': True, 'trial_receipt': str(session)},
                'summarize_gauge_trial.py': {},
                'install_battery_monitor.py': {'result': str(monitor / 'result.json')},
                'lynx_live_command.py': {},
                'configure_runtime_power.py': {'state': 'ready', 'result': 'fixture-power'},
                'collect_battery_session.py': {'state': 'watching', 'result': 'fixture-logger'},
                'sync_lynx_clock.py': {'passed': case != 'clock-failure', 'analysis': 'fixture-clock'},
                'configure_alpine_runtime.py': {'state': 'native-userspace-verified', 'result': 'fixture-alpine'},
            }
            if name not in responses:
                raise AssertionError('Unexpected external action: ' + name)
            if name == 'collect_battery_session.py':
                logger_started.append(True)
            if name in ['sync_lynx_clock.py', 'configure_alpine_runtime.py'] and not logger_started:
                raise AssertionError('Alpine stage attempted before host logger')
            if name == 'configure_alpine_runtime.py' and case == 'alpine-failure':
                rc = 1
            kwargs['stdout'].write(json.dumps(responses[name]).encode())
            return subprocess.CompletedProcess(argv, rc)

        argv = ['resume_battery_session.py', '--worker', str(worker), '--usb-unplugged-confirmed', '--runtime-power']
        if case != 'without-alpine':
            argv.extend(['--alpine-stage-receipt', str(stage)])
        with patch.object(resume, 'ROOT', root), patch.object(resume, 'PORT', port), \
                patch.object(sys, 'argv', argv), patch.object(resume.subprocess, 'run', fake_run):
            resume.main()
        result = json.loads((worker / 'result.json').read_text())
        expected = 'failed' if case.endswith('failure') else 'online'
        checks[case + '-state'] = result['state'] == expected
        checks[case + '-logger-preserved'] = bool(logger_started) and result['host_logger_receipt'] == 'fixture-logger'
        if case == 'without-alpine':
            checks['default-skips-alpine-and-clock'] = not any(name in calls for name in ['sync_lynx_clock.py', 'configure_alpine_runtime.py'])
        elif case == 'clock-failure':
            checks['clock-failure-stops-alpine-stage'] = 'configure_alpine_runtime.py' not in calls
        elif case == 'alpine-success':
            checks['logging-clock-alpine-order'] = calls.index('collect_battery_session.py') < calls.index('sync_lynx_clock.py') < calls.index('configure_alpine_runtime.py')
            checks['alpine-receipt-recorded'] = result['alpine_runtime_receipt'] == 'fixture-alpine'
        (worker / 'fixture-calls.json').write_text(json.dumps(calls, indent=2) + '\n')
    launcher_root = out / 'launcher'
    (launcher_root / 'logs').mkdir(parents=True)
    captured = []
    def fake_popen(argv, **kwargs):
        captured.append(argv)
        worker = Path(argv[argv.index('--worker') + 1])
        (worker / 'result.json').write_text(json.dumps({'state': 'waiting-native-ssh', 'listener_ready': True}))
        return SimpleNamespace(pid=123456)
    with patch.object(resume, 'ROOT', launcher_root), patch.object(sys, 'argv',
            ['resume_battery_session.py', '--start', '--usb-unplugged-confirmed', '--runtime-power', '--alpine-stage-receipt', str(stage)]), \
            patch.object(resume.subprocess, 'Popen', fake_popen):
        resume.main()
    checks['launcher-forwards-power-and-stage'] = len(captured) == 1 and '--runtime-power' in captured[0] and captured[0][-2:] == ['--alpine-stage-receipt', str(stage)]
    checks['launcher-forwards-usb-precondition'] = len(captured) == 1 and '--usb-unplugged-confirmed' in captured[0]
    report = {'passed': all(checks.values()), 'checks': checks, 'phone_contacted': False,
              'real_subprocesses_started': False,
              'limits': 'Worker ordering, propagation and failure reporting only; not hardware discovery, driver startup or logger behavior.'}
    (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'passed': report['passed'], 'checks': len(checks), 'result': str(out / 'result.json')}))
    if not report['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
