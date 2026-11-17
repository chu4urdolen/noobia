"""Guarded V47 boot_a-only trial and exact V46 restoration; no implicit reboot."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import time

import lynx_boot_a_v34_trial as base


ROOT = base.ROOT
PORT = ROOT / 'linux-port'
OUT = PORT / 'artifacts/wifi-dhcp-retry-v47-offline'
V47 = OUT / 'nord3-wifi-dhcp-retry-v47-untested.img'
V46 = PORT / 'artifacts/persistent-alpine-v46-offline/nord3-persistent-alpine-v46-untested.img'
V47_SHA = 'c969e1938b051ab03b49ad4f2260e900e9e336997d1026ca00c3a493dedde066'
V46_SHA = '6c487df1c16af1717e045167c165271065e9060c5a02b16b8e1b3ce3eca28f91'


def local():
    base.local('restore-v33')
    base.local('restore-v19')
    for path, digest in ((V46, V46_SHA), (V47, V47_SHA)):
        if not path.is_file() or path.stat().st_size != 67_108_864 or base.sha(path) != digest:
            raise ValueError('Working or trial image differs')
    build = json.loads((OUT / 'build-result.json').read_text())
    validation = json.loads((OUT / 'validation.json').read_text())
    fixtures = json.loads((OUT / 'dhcp-fixtures.json').read_text())
    if (build.get('state') != 'offline-v47-dhcp-retry-candidate-built' or
            validation.get('state') != 'offline-v47-validation-passed' or
            fixtures.get('state') != 'v47-dhcp-retry-fixtures-passed' or
            build.get('image_sha256') != V47_SHA or
            validation.get('image_sha256') != V47_SHA or
            build.get('parent_v46_sha256') != V46_SHA or
            validation.get('parent_v46_sha256') != V46_SHA):
        raise ValueError('V47 build, independent validation or fixtures differ')


def collector(path, max_elapsed):
    if path is None:
        raise ValueError('Fresh V47 pinned collector receipt required')
    path = path.resolve(strict=True)
    if not path.is_relative_to(ROOT / 'logs'):
        raise ValueError('Collector receipt outside Lynx logs')
    data = json.loads(path.read_text())
    if (data.get('state') != 'listening' or data.get('image_sha256') != V47_SHA or
            time.time_ns() - data.get('heartbeat_ns', 0) > 10_000_000_000 or
            data.get('elapsed_seconds', 9999) > max_elapsed):
        raise ValueError('V47 collector not fresh and listening')
    return str(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--prepare', action='store_true')
    mode.add_argument('--flash-v47', action='store_true')
    mode.add_argument('--reboot-after-v47', action='store_true')
    mode.add_argument('--restore-v46', action='store_true')
    parser.add_argument('--collector-receipt', type=Path)
    parser.add_argument('--flash-receipt', type=Path)
    args = parser.parse_args()
    local()
    commands = {
        'flash-v47': [str(base.FASTBOOT), '-s', base.SERIAL,
                      'flash', 'boot_a', str(V47)],
        'restore-v46': [str(base.FASTBOOT), '-s', base.SERIAL,
                        'flash', 'boot_a', str(V46)],
        'reboot-after-v47': [str(base.FASTBOOT), '-s', base.SERIAL, 'reboot'],
    }
    if args.prepare:
        print(json.dumps({'state': 'offline-ready-flash-held',
                          'trial_image_sha256': V47_SHA,
                          'working_v46_sha256': V46_SHA,
                          'trial_command': commands['flash-v47'],
                          'restoration_command': commands['restore-v46'],
                          'phone_contacted': False, 'flash_performed': False}))
        return
    action = ('flash-v47' if args.flash_v47 else
              'reboot-after-v47' if args.reboot_after_v47 else 'restore-v46')
    observer = (collector(args.collector_receipt, 90 if args.flash_v47 else 590)
                if not args.restore_v46 else None)
    if args.reboot_after_v47:
        if args.flash_receipt is None:
            parser.error('--reboot-after-v47 requires --flash-receipt')
        path = args.flash_receipt.resolve(strict=True)
        if not path.is_relative_to(ROOT / 'logs'):
            raise ValueError('Flash receipt outside Lynx logs')
        flashed = json.loads(path.read_text())
        if (flashed.get('state') != 'v47-flashed-no-reboot' or
                flashed.get('image_sha256') != V47_SHA or
                time.time_ns() - flashed.get('finished_ns', 0) > 24 * 3600 * 10**9):
            raise ValueError('Fresh complete V47 flash receipt required')
    os.umask(0o077)
    out = ROOT / 'logs' / f'v47-boot-a-trial-{time.time_ns()}'
    out.mkdir(mode=0o700)
    receipt = out / 'result.json'
    report = {'state': 'starting', 'created_ns': time.time_ns(),
              'mode': action, 'image_sha256': V46_SHA if args.restore_v46 else V47_SHA,
              'collector_receipt': observer, 'partition_scope': ['boot_a'],
              'slot_switch_allowed': False, 'operations': []}

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
        command = commands[action]
        event = {'command': command, 'state': 'issued',
                 'started_ns': time.time_ns(),
                 'started_monotonic': time.monotonic()}
        report['operations'].append(event)
        report['state'] = 'command-issued'
        save()
        run = subprocess.run(command, capture_output=True, text=True,
                             timeout=120 if action != 'reboot-after-v47' else 20)
        event.update(state='returned', finished_ns=time.time_ns(),
                     elapsed_seconds=time.monotonic() - event['started_monotonic'],
                     exit_code=run.returncode, output=run.stdout + run.stderr)
        save()
        if run.returncode:
            raise ValueError('Fastboot command failed; inspect exact output')
        report['state'] = ('v47-flashed-no-reboot' if args.flash_v47 else
                           'v46-restored-no-reboot' if args.restore_v46 else
                           'v47-reboot-requested')
    except Exception as exc:
        report.update(state='failed-or-incomplete', error=str(exc))
    report['finished_ns'] = time.time_ns()
    save()
    print(json.dumps({'state': report['state'], 'result': str(receipt)}))
    if report['state'] == 'failed-or-incomplete':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
