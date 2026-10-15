"""Start a bounded, detached gauge-trial listener and verify actual readiness.

The listener can contact Lynx if she emits the valid saved boot beacon.
No flashing; supervision and the existing USB-unplugged power cue still apply.
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--seconds', type=int, default=600)
    args = parser.parse_args()
    if not 30 <= args.seconds <= 600:
        raise ValueError('Listener deadline must be 30–600 seconds')
    os.umask(0o077)
    folder = ROOT / 'logs' / ('gauge-listener-launch-' + str(time.time_ns()))
    folder.mkdir(mode=0o700)
    tool = ROOT / 'tools/lynx_gauge_trial.py'
    command = [sys.executable, str(tool), '--listen', '--seconds', str(args.seconds)]
    with (folder / 'listener.stdout').open('wb') as stdout, (folder / 'listener.stderr').open('wb') as stderr:
        child = subprocess.Popen(command, cwd=ROOT, stdin=subprocess.DEVNULL,
                                 stdout=stdout, stderr=stderr, start_new_session=True)
    report = {'pid': child.pid, 'command': command, 'started_ns': time.time_ns(),
              'tool_sha256': hashlib.sha256(tool.read_bytes()).hexdigest(),
              'deadline_seconds': args.seconds, 'state': 'starting', 'ready_verified': False}
    receipt = folder / 'result.json'
    receipt.write_text(json.dumps(report, indent=2) + '\n')
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if child.poll() is not None:
            report.update(state='exited-before-ready', exit_code=child.returncode)
            break
        match = re.search(r'SENSOR LISTENER READY: ([^\n]+)', (folder / 'listener.stdout').read_text())
        if match:
            trial_receipt = Path(match.group(1)).resolve()
            if not trial_receipt.is_relative_to(ROOT / 'logs'):
                raise ValueError('Unexpected ready-receipt location')
            trial = json.loads(trial_receipt.read_text())
            stat = Path('/proc') / str(child.pid) / 'stat'
            start_ticks = int(stat.read_text().rsplit(')', 1)[1].split()[19])
            report.update(state='ready', ready_verified=True, ready_verified_ns=time.time_ns(),
                          process_start_ticks=start_ticks, trial_receipt=str(trial_receipt),
                          phone_already_contacted=trial['phone_contacted'])
            break
        time.sleep(0.1)
    if not report['ready_verified'] and report['state'] == 'starting':
        # Only our freshly spawned child; never leave an unready trial running.
        child.terminate()
        report['state'] = 'readiness-timeout-stop-requested'
    receipt.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'launcher_receipt': str(receipt), **report}, indent=2))
    if not report['ready_verified']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
