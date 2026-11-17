"""Guarded V34 boot_a-only Fastboot trial; V33/V19 rollback; no implicit reboot."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parent.parent
PORT = ROOT / 'linux-port'
V34 = PORT / 'artifacts/local-persistent-alpine-v34-offline/nord3-local-persistent-alpine-v34-untested.img'
V33 = PORT / 'artifacts/persistent-openrc-v33-offline/nord3-persistent-openrc-v33-untested.img'
V19 = PORT / 'artifacts/busybox-wifi-ssh-twostage-v19/nord3-busybox-candidate.img'
FASTBOOT = ROOT / 'tools/platform-tools/fastboot'
SERIAL = '89BYAY5L4T9HFUOV'
IMAGE_SHA = '727d72621e69743d2939540e84ca137183dae0055e07df458da52bddc60d13d4'
V33_SHA = '1d65456979d8a48d31de77c987b8aaf9b5ac11af62c51d00fdaff68ad47e747f'
V19_SHA = '5ce2dbf8a7c132fa7e31f6be70aa76f83afe8c293e2cd5f02251a532486fd851'
FASTBOOT_SHA = 'a686e2c7e8dc9cf4cba0cb8a2eef05f7b2bd682c925abd032fe203215d80b618'


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def local(action):
    if action == 'restore-v33':
        images = [(V33, V33_SHA)]
    elif action == 'restore-v19':
        images = [(V19, V19_SHA)]
    else:
        images = [(V34, IMAGE_SHA), (V33, V33_SHA), (V19, V19_SHA)]
    if any(not path.is_file() or path.stat().st_size != 67_108_864 or sha(path) != expected
           for path, expected in images):
        raise ValueError('Trial or rollback image differs')
    if sha(FASTBOOT) != FASTBOOT_SHA:
        raise ValueError('Pinned Fastboot binary differs')
    if action in ('restore-v33', 'restore-v19'):
        return
    build = json.loads((V34.parent / 'build-result.json').read_text())
    validation = json.loads((V34.parent / 'validation.json').read_text())
    exception = json.loads((PORT / 'docs/V34-TRIAL-EXCEPTION.json').read_text())
    if (build.get('state') != 'offline-autonomous-alpine-candidate-built' or
            validation.get('state') != 'offline-v34-validation-passed' or
            build['image_sha256'] != IMAGE_SHA or
            validation['image_sha256'] != IMAGE_SHA):
        raise ValueError('Offline V34 build/validation differs')
    if (exception.get('state') != 'prepared-not-executed' or
            exception.get('image_sha256') != IMAGE_SHA or
            exception.get('partition') != 'boot_a' or
            exception.get('other_partitions_allowed') is not False or
            exception.get('general_thermal_hold_remains_active') is not True):
        raise ValueError('Scoped V34 trial record differs')


def collector(path, max_elapsed):
    if path is None:
        raise ValueError('Fresh V34 pinned collector receipt required')
    path = path.resolve(strict=True)
    if not path.is_relative_to(ROOT / 'logs'):
        raise ValueError('Collector receipt outside Lynx logs')
    record = json.loads(path.read_text())
    if (record.get('state') != 'listening' or
            record.get('image_sha256') != IMAGE_SHA or
            time.time_ns() - record.get('heartbeat_ns', 0) > 10_000_000_000 or
            record.get('elapsed_seconds', 9999) > max_elapsed):
        raise ValueError('V34 collector not fresh and listening')
    return str(path)


def preflight():
    process = subprocess.run(['python3', str(ROOT / 'tools/lynx_fastboot_preflight.py'), '--connect'],
                             capture_output=True, text=True, timeout=120)
    if process.returncode:
        raise ValueError('Fresh Fastboot preflight refused: ' +
                         process.stdout[-500:] + process.stderr[-500:])
    result = json.loads(process.stdout)
    if (not result['identity_and_slot_match'] or
            not result['partition_layout_match'] or
            int(result['values']['max-download-size'], 16) < 67_108_864):
        raise ValueError('Fastboot identity, slot, layout or download limit differs')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--prepare', action='store_true')
    mode.add_argument('--flash-v34', action='store_true')
    mode.add_argument('--restore-v33', action='store_true')
    mode.add_argument('--restore-v19', action='store_true')
    mode.add_argument('--reboot-after-v34', action='store_true')
    parser.add_argument('--collector-receipt', type=Path)
    parser.add_argument('--flash-receipt', type=Path)
    args = parser.parse_args()
    action = ('prepare' if args.prepare else 'flash-v34' if args.flash_v34 else
              'restore-v33' if args.restore_v33 else
              'restore-v19' if args.restore_v19 else 'reboot-after-v34')
    local(action)
    if args.prepare:
        print(json.dumps({'state': 'offline-ready-flash-held',
                          'trial_command': [str(FASTBOOT), '-s', SERIAL, 'flash', 'boot_a', str(V34)],
                          'rollback_v33': [str(FASTBOOT), '-s', SERIAL, 'flash', 'boot_a', str(V33)],
                          'rollback_v19': [str(FASTBOOT), '-s', SERIAL, 'flash', 'boot_a', str(V19)],
                          'phone_contacted': False, 'flash_performed': False}))
        return
    if args.flash_v34 or args.reboot_after_v34:
        collector_path = collector(args.collector_receipt,
                                   590 if args.reboot_after_v34 else 90)
    else:
        collector_path = None
    if args.reboot_after_v34:
        if args.flash_receipt is None:
            parser.error('--reboot-after-v34 requires --flash-receipt')
        flash_path = args.flash_receipt.resolve(strict=True)
        if not flash_path.is_relative_to(ROOT / 'logs'):
            raise ValueError('Flash receipt outside Lynx logs')
        flashed = json.loads(flash_path.read_text())
        if (flashed.get('state') != 'v34-flashed-no-reboot' or
                flashed.get('image_sha256') != IMAGE_SHA or
                time.time_ns() - flashed.get('finished_ns', 0) > 24 * 60 * 60 * 10**9):
            raise ValueError('Fresh completed V34 flash receipt required')
    os.umask(0o077)
    out = ROOT / 'logs' / ('v34-boot-a-trial-' + str(time.time_ns()))
    out.mkdir(mode=0o700)
    report = {'state': 'starting', 'created_ns': time.time_ns(),
              'mode': action,
              'image_sha256': (IMAGE_SHA if args.flash_v34 or args.reboot_after_v34 else
                               V33_SHA if args.restore_v33 else V19_SHA),
              'collector_receipt': collector_path,
              'partition_scope': ['boot_a'], 'slot_switch_allowed': False,
              'operations': []}

    def save():
        temp = out / 'result.tmp'
        temp.write_text(json.dumps(report, indent=2) + '\n')
        temp.replace(out / 'result.json')

    save()
    try:
        fresh = preflight()
        report.update(state='fastboot-preflight-passed', preflight_receipt=fresh['report'])
        save()
        if args.reboot_after_v34:
            command = [str(FASTBOOT), '-s', SERIAL, 'reboot']
        else:
            image = V34 if args.flash_v34 else V33 if args.restore_v33 else V19
            command = [str(FASTBOOT), '-s', SERIAL, 'flash', 'boot_a', str(image)]
        event = {'command': command, 'state': 'issued', 'started_ns': time.time_ns(),
                 'started_monotonic': time.monotonic()}
        report['operations'].append(event)
        report['state'] = 'command-issued'; save()
        result = subprocess.run(command, capture_output=True, text=True,
                                timeout=20 if args.reboot_after_v34 else 120)
        event.update(state='returned', finished_ns=time.time_ns(),
                     elapsed_seconds=time.monotonic() - event['started_monotonic'],
                     exit_code=result.returncode, output=result.stdout + result.stderr)
        save()
        if result.returncode:
            raise ValueError('Fastboot command failed; inspect exact output')
        report['state'] = ('v34-flashed-no-reboot' if args.flash_v34 else
                           'v33-restored-no-reboot' if args.restore_v33 else
                           'v19-restored-no-reboot' if args.restore_v19 else
                           'v34-reboot-requested')
    except Exception as error:
        report.update(state='failed-or-incomplete', error=str(error))
    report['finished_ns'] = time.time_ns(); save()
    print(json.dumps({'state': report['state'], 'result': str(out / 'result.json')}))
    if report['state'] == 'failed-or-incomplete':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
