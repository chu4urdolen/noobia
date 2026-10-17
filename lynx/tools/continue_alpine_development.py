"""After the guarded resume workflow, add and verify a RAM development layer."""
import argparse
import hashlib
import json
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run(report, out, name, argv, timeout=180, stdin=None):
    record = {'name': name, 'argv': list(map(str, argv)), 'started_ns': time.time_ns()}
    report['operations'].append(record)
    with (out / (name + '.stdout')).open('wb') as stdout, (out / (name + '.stderr')).open('wb') as stderr:
        result = subprocess.run(list(map(str, argv)), cwd=ROOT, stdin=stdin,
                                stdout=stdout, stderr=stderr, timeout=timeout)
    record.update(exit_code=result.returncode, finished_ns=time.time_ns())
    if result.returncode:
        raise RuntimeError(name + ' failed; output retained')
    return (out / (name + '.stdout')).read_bytes()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--resume-receipt', type=Path, required=True)
    parser.add_argument('--wait-seconds', type=int, default=660)
    args = parser.parse_args()
    if not 30 <= args.wait_seconds <= 900:
        parser.error('--wait-seconds must be between 30 and 900')
    resume_path = args.resume_receipt.resolve(strict=True)
    os.umask(0o077)
    out = ROOT / 'logs' / ('alpine-development-continuation-' + str(time.time_ns()))
    out.mkdir(mode=0o700)
    report = {'state': 'waiting-for-guarded-resume', 'resume_receipt': str(resume_path),
              'started_ns': time.time_ns(), 'operations': [], 'flash_performed': False,
              'partition_written': False, 'phone_shutdown': False}

    def save():
        (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')

    save()
    deadline = time.monotonic() + args.wait_seconds
    try:
        while True:
            resume = json.loads(resume_path.read_text())
            state = resume.get('state')
            if state == 'online':
                break
            if state == 'failed':
                raise RuntimeError('Guarded resume ended failed: ' + str(resume.get('error', 'unknown')))
            if time.monotonic() >= deadline:
                raise TimeoutError('Guarded resume did not reach online before deadline')
            time.sleep(2)
        session = Path(resume['session']).resolve(strict=True)
        alpine_trial = Path(resume['alpine_runtime_receipt']).resolve(strict=True)
        native = json.loads(session.read_text())
        trial = json.loads(alpine_trial.read_text())
        if not (native.get('native_identity_verified') and native.get('session_left_running')
                and trial.get('native_rootfs_verified') and trial.get('rootfs_left_in_ram')):
            raise ValueError('Current native session and installed Alpine receipt are required')
        boot_id = trial['boot_id']
        report.update(state='installing-development-layer', session=str(session),
                      alpine_runtime_receipt=str(alpine_trial), boot_id=boot_id)
        save()

        power = run(report, out, 'power-before', [sys.executable, ROOT / 'tools/configure_runtime_power.py',
                    '--session', session, '--verify-only'])
        if json.loads(power)['state'] != 'ready':
            raise ValueError('Runtime power/watcher verification failed')
        command = '/bin/busybox sh -s -- ' + boot_id
        meta = run(report, out, 'development-install', [sys.executable, ROOT / 'tools/lynx_live_command.py',
                    '--session', session, '--name', 'alpine-development', '--timeout', '60',
                    '--stdin-file', ROOT / 'linux-port/alpine-development.sh', '--command', command])
        live = json.loads(meta)
        capture = Path(live['capture']).read_bytes()
        if not live.get('native_identity_verified') or live.get('command_exit_code') != 0 or b'LYNX_ALPINE_DEVELOPMENT_PASS' not in capture:
            raise ValueError('Development installation lacks a successful native proof')
        report['development_capture'] = str(live['capture'])
        save()

        diagnostic = ROOT / 'linux-port/lynx-system-report.py'
        diagnostic_sha = hashlib.sha256(diagnostic.read_bytes()).hexdigest()
        root = '/run/lynx/alpine-3.24.2'
        target = root + '/root/work/lynx-system-report.py'
        remote = ('set -eu; test "$(cat /proc/sys/kernel/random/boot_id)" = ' + boot_id +
                  '; test ! -e ' + shlex.quote(target) + '; /bin/busybox chroot ' + root +
                  ' /bin/busybox mkdir -p /root/work; cat > ' + shlex.quote(target) +
                  '; echo "' + diagnostic_sha + '  ' + target + '" | /bin/busybox sha256sum -c -; ' +
                  '/bin/busybox chroot ' + root + ' /usr/bin/python3 /root/work/lynx-system-report.py; ' +
                  'echo LYNX_SYSTEM_REPORT_PASS')
        diagnostic_meta = run(report, out, 'system-report', [sys.executable, ROOT / 'tools/lynx_live_command.py',
                  '--session', session, '--name', 'alpine-system-report', '--timeout', '30',
                  '--stdin-file', diagnostic, '--command', remote])
        diagnostic_result = json.loads(diagnostic_meta)
        diagnostic_capture = Path(diagnostic_result['capture']).read_bytes()
        if (not diagnostic_result.get('native_identity_verified')
                or diagnostic_result.get('command_exit_code') != 0
                or b'LYNX_SYSTEM_REPORT_PASS' not in diagnostic_capture):
            raise ValueError('Native Python diagnostic report failed its identity or marker check')
        report['system_report_capture'] = str(diagnostic_result['capture'])
        save()

        report['state'] = 'capturing-checkpoint'; save()
        checkpoint_raw = run(report, out, 'checkpoint', [sys.executable, ROOT / 'tools/checkpoint_alpine_runtime.py',
                    '--session', session, '--rootfs-trial', alpine_trial, '--capture'], timeout=240)
        checkpoint_info = json.loads(checkpoint_raw)
        if checkpoint_info.get('state') != 'checkpoint-verified':
            raise ValueError('Development userspace checkpoint failed')
        checkpoint = Path(checkpoint_info['result']).resolve(strict=True)
        report['checkpoint_receipt'] = str(checkpoint)
        save()

        report['state'] = 'testing-checkpoint-restore'; save()
        restore_raw = run(report, out, 'restore-test', [sys.executable, ROOT / 'tools/test_alpine_checkpoint_restore.py',
                    '--checkpoint', checkpoint], timeout=120)
        restore_info = json.loads(restore_raw)
        restore = Path(restore_info['result']).resolve(strict=True)
        restore_result = json.loads(restore.read_text())
        if restore_result.get('state') != 'restoration-verified' or not restore_result.get('development_tools_present'):
            raise ValueError('Restored development layer did not pass the stock-kernel VM checks')
        checkpoint_result = json.loads(checkpoint.read_text())
        checkpoint_result.update(restoration_tested=True, restore_validation=str(restore),
                                 restore_validation_sha256=hashlib.sha256(restore.read_bytes()).hexdigest())
        temp = checkpoint.with_suffix('.tmp')
        temp.write_text(json.dumps(checkpoint_result, indent=2) + '\n')
        temp.replace(checkpoint)
        report.update(state='development-and-restore-verified', restore_validation=str(restore),
                      finished_ns=time.time_ns(), limits='RAM userspace on Lynx; snapshot restore tested only in isolated QEMU with the exact stock kernel.')
        save()
        print(json.dumps({'state': report['state'], 'result': str(out / 'result.json'),
                          'checkpoint': str(checkpoint), 'restore_validation': str(restore)}))
    except Exception as error:
        report.update(state='failed', error=str(error), finished_ns=time.time_ns())
        save()
        print(json.dumps({'state': report['state'], 'result': str(out / 'result.json'), 'error': str(error)}))
        raise SystemExit(1)


if __name__ == '__main__':
    main()
