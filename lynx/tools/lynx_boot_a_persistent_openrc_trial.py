"""Guarded V29 boot_a-only Fastboot trial and V19 rollback; no implicit reboot."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parent.parent
PORT = ROOT / 'linux-port'
V29 = PORT / 'artifacts/persistent-openrc-v29-offline/nord3-persistent-openrc-untested.img'
V19 = PORT / 'artifacts/busybox-wifi-ssh-twostage-v19/nord3-busybox-candidate.img'
FASTBOOT = ROOT / 'tools/platform-tools/fastboot'
SERIAL = '89BYAY5L4T9HFUOV'
EXCEPTION = PORT / 'docs/V29-TRIAL-EXCEPTION.json'
IMAGE_SHA = '2483ba8d5ee43ef2ba692885682b9ebacc59fdb8216700eaad1eff7c531b3048'
V19_SHA = '5ce2dbf8a7c132fa7e31f6be70aa76f83afe8c293e2cd5f02251a532486fd851'


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def check_local():
    if (sha(V29) != IMAGE_SHA or sha(V19) != V19_SHA or
            V29.stat().st_size != 67_108_864 or V19.stat().st_size != 67_108_864):
        raise ValueError('V29 trial or V19 rollback image differs')
    ready = json.loads((ROOT / 'logs/persistent-openrc-offline-readiness-1792423153966857655/result.json').read_text())
    if (ready.get('state') != 'offline-recovery-ready-linux-flash-held' or
            ready['images'][0]['sha256'] != IMAGE_SHA or
            ready['images'][1]['sha256'] != V19_SHA or
            sha(FASTBOOT) != ready['fastboot_sha256']):
        raise ValueError('Offline recovery receipt or Fastboot binary differs')
    exception = json.loads(EXCEPTION.read_text())
    if (exception.get('state') != 'prepared-not-executed' or
            exception.get('image_sha256') != IMAGE_SHA or
            exception.get('partition') != 'boot_a' or
            exception.get('other_partitions_allowed') is not False or
            exception.get('general_thermal_hold_remains_active') is not True):
        raise ValueError('Scoped V29 exception differs')


def check_collector(path, *, max_elapsed=90):
    if path is None:
        raise ValueError('Fresh pinned network collector receipt required')
    path = path.resolve(strict=True)
    if not path.is_relative_to(ROOT / 'logs'):
        raise ValueError('Collector receipt escaped Lynx logs')
    collector = json.loads(path.read_text())
    build = json.loads((PORT / 'artifacts/busybox-wifi-ssh-twostage-v19/build-validation.json').read_text())
    if (collector.get('state') != 'listening' or
            collector.get('session_token') != build['session_token'] or
            time.time_ns() - collector.get('heartbeat_ns', 0) > 10_000_000_000 or
            collector.get('elapsed_seconds', 9999) > max_elapsed):
        raise ValueError('Collector is not fresh and listening')
    return str(path)


def preflight():
    process = subprocess.run(['python3', str(ROOT / 'tools/lynx_fastboot_preflight.py'), '--connect'],
                             capture_output=True, text=True, timeout=120)
    if process.returncode:
        raise ValueError('Fresh Fastboot preflight refused: ' + process.stdout[-500:] + process.stderr[-500:])
    summary = json.loads(process.stdout)
    if (not summary['identity_and_slot_match'] or
            not summary['partition_layout_match'] or
            int(summary['values']['max-download-size'], 16) < 67_108_864):
        raise ValueError('Fastboot serial, slot, partition layout or download limit differs')
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--prepare', action='store_true')
    mode.add_argument('--flash-v29', action='store_true')
    mode.add_argument('--restore-v19', action='store_true')
    mode.add_argument('--reboot-after-v29', action='store_true')
    parser.add_argument('--collector-receipt', type=Path)
    parser.add_argument('--flash-receipt', type=Path)
    args = parser.parse_args()
    check_local()
    if args.prepare:
        print(json.dumps({'state': 'offline-ready-flash-held',
                          'trial_command': [str(FASTBOOT), '-s', SERIAL, 'flash', 'boot_a', str(V29)],
                          'rollback_command': [str(FASTBOOT), '-s', SERIAL, 'flash', 'boot_a', str(V19)],
                          'phone_contacted': False, 'flash_performed': False}))
        return
    if args.flash_v29 or args.reboot_after_v29:
        collector_path = check_collector(args.collector_receipt,
                                         max_elapsed=590 if args.reboot_after_v29 else 90)
    else:
        collector_path = None
    if args.reboot_after_v29:
        if args.flash_receipt is None:
            parser.error('--reboot-after-v29 requires --flash-receipt')
        flash_path = args.flash_receipt.resolve(strict=True)
        if not flash_path.is_relative_to(ROOT / 'logs'):
            raise ValueError('Flash receipt escaped Lynx logs')
        flashed = json.loads(flash_path.read_text())
        if (flashed.get('state') != 'v29-flashed-no-reboot' or
                flashed.get('image_sha256') != IMAGE_SHA or
                time.time_ns() - flashed.get('finished_ns', 0) > 24 * 60 * 60 * 10**9):
            raise ValueError('Fresh completed V29 flash receipt required')
    os.umask(0o077)
    out = ROOT / 'logs' / ('v29-boot-a-trial-' + str(time.time_ns()))
    out.mkdir(mode=0o700)
    report = {'state': 'starting', 'created_ns': time.time_ns(),
              'mode': ('flash-v29' if args.flash_v29 else 'restore-v19' if args.restore_v19 else 'reboot-after-v29'),
              'image_sha256': IMAGE_SHA if not args.restore_v19 else V19_SHA,
              'collector_receipt': collector_path,
              'partition_scope': ['boot_a'], 'slot_switch_allowed': False,
              'operations': []}

    def save():
        temporary = out / 'result.tmp'
        temporary.write_text(json.dumps(report, indent=2) + '\n')
        temporary.replace(out / 'result.json')

    save()
    try:
        fresh = preflight()
        report.update(state='fastboot-preflight-passed', preflight_receipt=fresh['report'])
        save()
        if args.reboot_after_v29:
            command = [str(FASTBOOT), '-s', SERIAL, 'reboot']
        else:
            image = V29 if args.flash_v29 else V19
            command = [str(FASTBOOT), '-s', SERIAL, 'flash', 'boot_a', str(image)]
        event = {'command': command, 'state': 'issued', 'started_ns': time.time_ns(),
                 'started_monotonic': time.monotonic()}
        report['operations'].append(event)
        report['state'] = 'command-issued'
        save()
        process = subprocess.run(command, capture_output=True, text=True,
                                 timeout=120 if not args.reboot_after_v29 else 20)
        event.update(state='returned', finished_ns=time.time_ns(),
                     elapsed_seconds=time.monotonic() - event['started_monotonic'],
                     exit_code=process.returncode, output=process.stdout + process.stderr)
        save()
        if process.returncode:
            raise ValueError('Fastboot command failed; inspect exact output')
        report['state'] = ('v29-flashed-no-reboot' if args.flash_v29 else
                           'v19-restored-no-reboot' if args.restore_v19 else
                           'v29-reboot-requested')
    except Exception as error:
        report.update(state='failed-or-incomplete', error=str(error))
    report['finished_ns'] = time.time_ns()
    save()
    print(json.dumps({'state': report['state'], 'result': str(out / 'result.json')}))
    if report['state'] == 'failed-or-incomplete':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
