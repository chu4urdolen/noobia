"""Arm a bounded fresh-V19 listener, then run the RAM-only health stage.

Start this BEFORE the physical reboot. The detached worker waits up to 900 s
for the existing pinned V19 beacon and records both listener and trial receipts.
It never flashes or changes a phone partition.
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HERE = Path(__file__).resolve().parent


def save(path, report):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(report, indent=2) + '\n')
    temporary.replace(path)


def worker(out):
    out = out.resolve(strict=True)
    if not out.is_relative_to(ROOT / 'logs'):
        raise ValueError('Trial window escaped Lynx logs')
    report_path = out / 'result.json'
    report = json.loads(report_path.read_text())
    if not report.get('usb_unplugged_confirmed') or report.get('state') != 'starting':
        raise ValueError('Trial window lacks physical precondition or was already started')
    listener = None
    try:
        with (out / 'listener.stdout').open('wb') as stdout, \
                (out / 'listener.stderr').open('wb') as stderr:
            listener = subprocess.Popen(
                [sys.executable, str(HERE / 'lynx_wifi_v19_contact.py'),
                 '--listen', '--seconds', '900'],
                stdout=stdout, stderr=stderr, stdin=subprocess.DEVNULL,
                cwd=ROOT)
            report['listener_pid'] = listener.pid
            deadline = time.monotonic() + 12
            while time.monotonic() < deadline:
                raw = (out / 'listener.stdout').read_text(errors='replace')
                lines = [line for line in raw.splitlines() if line.startswith('LISTENER READY: ')]
                if lines:
                    receipt = Path(lines[-1].removeprefix('LISTENER READY: ')).resolve(strict=True)
                    if not receipt.is_relative_to(ROOT / 'logs'):
                        raise ValueError('Listener receipt escaped Lynx logs')
                    report.update(state='listening', contact_receipt=str(receipt), ready_ns=time.time_ns())
                    save(report_path, report)
                    break
                if listener.poll() is not None:
                    raise ValueError('Pinned listener exited before readiness')
                time.sleep(.1)
            else:
                raise TimeoutError('Pinned listener did not become ready')
            listener.wait(timeout=920)
        contact = json.loads(Path(report['contact_receipt']).read_text())
        report['contact_state'] = contact.get('state')
        report['contact_native_ssh_verified'] = contact.get('native_ssh_verified', False)
        if contact.get('state') != 'native-ssh-available':
            report['state'] = 'closed-without-verified-v19-contact'
            return
        report['state'] = 'running-ram-health-trial'
        save(report_path, report)
        command = [sys.executable, str(HERE / 'launch_autonomous_health_ram_trial.py'),
                   '--run', '--contact-receipt', report['contact_receipt'],
                   '--usb-unplugged-confirmed']
        with (out / 'trial.stdout').open('wb') as stdout, \
                (out / 'trial.stderr').open('wb') as stderr:
            trial = subprocess.run(command, stdout=stdout, stderr=stderr,
                                   stdin=subprocess.DEVNULL, cwd=ROOT, timeout=230)
        report['trial_exit_code'] = trial.returncode
        messages = (out / 'trial.stdout').read_text(errors='replace').splitlines()
        for line in reversed(messages):
            try:
                response = json.loads(line)
            except json.JSONDecodeError:
                continue
            if response.get('result'):
                report['trial_receipt'] = response['result']
                break
        report['state'] = 'ram-health-trial-complete' if trial.returncode == 0 else 'ram-health-trial-failed'
        if trial.returncode == 0:
            with (out / 'logger.stdout').open('wb') as stdout, \
                    (out / 'logger.stderr').open('wb') as stderr:
                logger = subprocess.run(
                    [sys.executable, str(HERE / 'collect_battery_session.py'),
                     '--session', report['contact_receipt'], '--seconds', '14400'],
                    stdout=stdout, stderr=stderr, stdin=subprocess.DEVNULL,
                    cwd=ROOT, timeout=12)
            report['host_logger_start_exit_code'] = logger.returncode
            if logger.returncode == 0:
                for line in reversed((out / 'logger.stdout').read_text().splitlines()):
                    try:
                        launched = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    report['host_logger_receipt'] = launched.get('result')
                    break
    except Exception as exc:
        report.update(state='worker-failed', error=str(exc))
        if listener and listener.poll() is None:
            listener.terminate()
    finally:
        report['finished_ns'] = time.time_ns()
        save(report_path, report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--arm', action='store_true')
    mode.add_argument('--worker', type=Path)
    parser.add_argument('--usb-unplugged-confirmed', action='store_true')
    args = parser.parse_args()
    os.umask(0o077)
    if args.worker:
        worker(args.worker)
        return
    if not args.usb_unplugged_confirmed:
        parser.error('--arm requires current physical confirmation that USB is unplugged')
    out = ROOT / 'logs' / ('autonomous-health-window-' + str(time.time_ns()))
    out.mkdir(mode=0o700)
    report_path = out / 'result.json'
    report = {'state': 'starting', 'created_ns': time.time_ns(),
              'usb_unplugged_confirmed': True, 'partition_writes': False,
              'flash_performed': False, 'phone_contacted_at_arm': False,
              'listener_seconds': 900}
    save(report_path, report)
    with (out / 'worker.stdout').open('wb') as stdout, \
            (out / 'worker.stderr').open('wb') as stderr:
        child = subprocess.Popen([sys.executable, str(Path(__file__).resolve()),
                                  '--worker', str(out)],
                                 stdout=stdout, stderr=stderr,
                                 stdin=subprocess.DEVNULL, start_new_session=True,
                                 cwd=ROOT)
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        report = json.loads(report_path.read_text())
        if report['state'] == 'listening':
            print(json.dumps({'state': 'listener-ready-before-physical-reboot',
                              'result': str(report_path), 'worker_pid': child.pid}))
            return
        if child.poll() is not None:
            raise SystemExit('Window worker failed before readiness: ' + str(report_path))
        time.sleep(.1)
    raise SystemExit('Window did not become ready: ' + str(report_path))


if __name__ == '__main__':
    main()
