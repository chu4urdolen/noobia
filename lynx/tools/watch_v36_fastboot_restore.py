"""Wait for Lynx Fastboot, then run the pinned boot_a-only V33 rollback.

The rollback tool checks identity, slot and layout again. This watcher never
reboots the phone and stops after one successful restoration or a deadline.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time

import lynx_boot_a_v34_trial as rollback

ROOT = Path(__file__).resolve().parent.parent


def save(path, report):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(report, indent=2) + '\n')
    tmp.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds', type=int, default=900)
    args = parser.parse_args()
    if not 1 <= args.seconds <= 1800:
        parser.error('--seconds must be 1..1800')
    rollback.local('restore-v33')
    os.umask(0o077)
    out = ROOT / 'logs' / ('v36-fastboot-restore-watch-' + str(time.time_ns()))
    out.mkdir(mode=0o700)
    receipt = out / 'result.json'
    report = {'state': 'waiting-for-fastboot', 'started_ns': time.time_ns(),
              'seconds': args.seconds, 'serial': rollback.SERIAL,
              'rollback_image_sha256': rollback.V33_SHA,
              'partition_scope': ['boot_a'], 'slot_switch_allowed': False,
              'reboot_allowed': False, 'polls': 0}
    save(receipt, report)
    print('V36 ROLLBACK WATCH READY:', receipt, flush=True)
    deadline = time.monotonic() + args.seconds
    while time.monotonic() < deadline:
        report['heartbeat_ns'] = time.time_ns()
        report['polls'] += 1
        try:
            probe = subprocess.run([str(rollback.FASTBOOT), 'devices', '-l'],
                                   capture_output=True, text=True, timeout=8)
            if probe.returncode == 0 and any(
                    line.split() and line.split()[0] == rollback.SERIAL
                    for line in probe.stdout.splitlines()):
                report.update(state='exact-serial-seen', seen_ns=time.time_ns())
                save(receipt, report)
                command = ['python3', str(ROOT / 'tools/lynx_boot_a_v34_trial.py'),
                           '--restore-v33']
                result = subprocess.run(command, capture_output=True, text=True,
                                        timeout=180)
                (out / 'guarded-restore.raw').write_text(result.stdout + result.stderr)
                report.update(state='v33-restored-no-reboot' if result.returncode == 0
                              else 'guarded-restore-refused', finished_ns=time.time_ns(),
                              restore_exit_code=result.returncode)
                save(receipt, report)
                print(json.dumps({'state': report['state'], 'receipt': str(receipt)}),
                      flush=True)
                return
        except subprocess.TimeoutExpired:
            report['last_poll_timeout_ns'] = time.time_ns()
        save(receipt, report)
        time.sleep(2)
    report.update(state='deadline-without-fastboot', finished_ns=time.time_ns())
    save(receipt, report)
    print(json.dumps({'state': report['state'], 'receipt': str(receipt)}), flush=True)


if __name__ == '__main__':
    main()
