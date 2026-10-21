"""Guarded boot_a-only V38 persistent-stage trial; no implicit reboot."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time

import lynx_boot_a_v34_trial as base

ROOT = base.ROOT
V38 = ROOT / 'linux-port/artifacts/persistent-trace-v38-offline/nord3-persistent-trace-v38-untested.img'
BUILD = V38.parent / 'build-result.json'
VALIDATION = V38.parent / 'validation.json'
IMAGE_SHA = 'ba1176676174bef30d111bff51139f238117f89e416b7fa72c2619f53396b8ad'


def local():
    base.local('restore-v33')  # Exact V33 rollback and pinned Fastboot.
    base.local('restore-v19')  # Independent BusyBox rescue rollback.
    build = json.loads(BUILD.read_text())
    validation = json.loads(VALIDATION.read_text())
    if (not V38.is_file() or V38.stat().st_size != 67_108_864 or
            base.sha(V38) != IMAGE_SHA or
            build['state'] != 'offline-persistent-trace-diagnostic-built' or
            validation['state'] != 'offline-v38-validation-passed' or
            build['image_sha256'] != IMAGE_SHA or
            validation['image_sha256'] != IMAGE_SHA):
        raise ValueError('V38 image, validation or rollback differs')


def collector(path, max_elapsed):
    if path is None:
        raise ValueError('Fresh V38 pinned collector receipt required')
    path = path.resolve(strict=True)
    if not path.is_relative_to(ROOT / 'logs'):
        raise ValueError('Collector receipt outside Lynx logs')
    record = json.loads(path.read_text())
    if (record.get('state') != 'listening' or
            record.get('image_sha256') != IMAGE_SHA or
            time.time_ns() - record.get('heartbeat_ns', 0) > 10_000_000_000 or
            record.get('elapsed_seconds', 9999) > max_elapsed):
        raise ValueError('V38 collector not fresh and listening')
    return str(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--prepare', action='store_true')
    mode.add_argument('--flash-v38', action='store_true')
    mode.add_argument('--reboot-after-v38', action='store_true')
    parser.add_argument('--collector-receipt', type=Path)
    parser.add_argument('--flash-receipt', type=Path)
    args = parser.parse_args()
    local()
    if args.prepare:
        print(json.dumps({'state': 'offline-ready-flash-held',
                          'image_sha256': IMAGE_SHA,
                          'trial_command': [str(base.FASTBOOT), '-s', base.SERIAL,
                                            'flash', 'boot_a', str(V38)],
                          'rollback_v33': [str(base.FASTBOOT), '-s', base.SERIAL,
                                           'flash', 'boot_a', str(base.V33)],
                          'phone_contacted': False, 'flash_performed': False}))
        return
    contact = collector(args.collector_receipt, 90 if args.flash_v38 else 590)
    if args.reboot_after_v38:
        if args.flash_receipt is None:
            parser.error('--reboot-after-v38 requires --flash-receipt')
        path = args.flash_receipt.resolve(strict=True)
        if not path.is_relative_to(ROOT / 'logs'):
            raise ValueError('Flash receipt outside Lynx logs')
        flashed = json.loads(path.read_text())
        if (flashed.get('state') != 'v38-flashed-no-reboot' or
                flashed.get('image_sha256') != IMAGE_SHA or
                time.time_ns() - flashed.get('finished_ns', 0) > 24 * 3600 * 10**9):
            raise ValueError('Fresh completed V38 flash receipt required')
    os.umask(0o077)
    out = ROOT / 'logs' / ('v38-boot-a-trial-' + str(time.time_ns()))
    out.mkdir(mode=0o700)
    receipt = out / 'result.json'
    report = {'state': 'starting', 'created_ns': time.time_ns(),
              'mode': 'flash-v38' if args.flash_v38 else 'reboot-after-v38',
              'image_sha256': IMAGE_SHA, 'collector_receipt': contact,
              'partition_scope': ['boot_a'], 'slot_switch_allowed': False,
              'operations': []}

    def save():
        temp = receipt.with_suffix('.tmp')
        temp.write_text(json.dumps(report, indent=2) + '\n')
        temp.replace(receipt)

    save()
    try:
        fresh = base.preflight()
        report.update(state='fastboot-preflight-passed',
                      preflight_receipt=fresh['report'])
        save()
        command = ([str(base.FASTBOOT), '-s', base.SERIAL, 'flash', 'boot_a', str(V38)]
                   if args.flash_v38 else
                   [str(base.FASTBOOT), '-s', base.SERIAL, 'reboot'])
        event = {'command': command, 'state': 'issued',
                 'started_ns': time.time_ns(), 'started_monotonic': time.monotonic()}
        report['operations'].append(event)
        report['state'] = 'command-issued'
        save()
        result = subprocess.run(command, capture_output=True, text=True,
                                timeout=120 if args.flash_v38 else 20)
        event.update(state='returned', finished_ns=time.time_ns(),
                     elapsed_seconds=time.monotonic() - event['started_monotonic'],
                     exit_code=result.returncode,
                     output=result.stdout + result.stderr)
        save()
        if result.returncode:
            raise ValueError('Fastboot command failed; inspect exact output')
        report['state'] = ('v38-flashed-no-reboot' if args.flash_v38 else
                           'v38-reboot-requested')
    except Exception as error:
        report.update(state='failed-or-incomplete', error=str(error))
    report['finished_ns'] = time.time_ns()
    save()
    print(json.dumps({'state': report['state'], 'result': str(receipt)}))
    if report['state'] == 'failed-or-incomplete':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
