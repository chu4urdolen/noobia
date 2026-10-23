"""Prepare or apply a guarded rollback of optional Alpine maintenance services."""

import argparse
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import subprocess
import time

from lynx_wifi_v19_contact import ssh_command

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / 'linux-port/artifacts/persistent-alpine-v46-offline/build-result.json'
SERVICES = ('lynx-maintenance', 'lynx-local-logs', 'lynx-battery-reserve')
KERNEL = '5.10.149-android12-9-o-g311738fbb5a8'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ip', required=True)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--prepared', type=Path)
    args = parser.parse_args()
    try:
        in_network = (ipaddress.ip_address(args.ip) in
                      ipaddress.ip_network('192.168.100.0/24') and
                      not ipaddress.ip_address(args.ip).is_multicast and
                      args.ip not in ('192.168.100.0', '192.168.100.255'))
    except ValueError:
        in_network = False
    if not in_network:
        raise ValueError('IP outside pinned Noobia handset range')
    if args.apply != bool(args.prepared):
        raise ValueError('Apply requires --prepared; prepare omits both flags')
    build = json.loads(BUILD.read_text())
    if build.get('state') != 'offline-persistent-alpine-built':
        raise ValueError('V46 build record missing')
    init_sha = build['init_sha256']
    root = '/run/lynx/persistent-alpine'
    preflight = (
        'set -eu; '
        f'test "$(uname -r)" = "{KERNEL}"; '
        f'test "$(sha256sum /init | cut -c1-64)" = "{init_sha}"; '
        f'test "$(readlink /proc/1/exe)" = {root}/sbin/openrc-init; '
        f'test -d {root}/etc/runlevels/default; '
        'boot_id=$(cat /proc/sys/kernel/random/boot_id); '
        'case "$boot_id" in ""|*[!0-9a-f-]*) exit 1;; esac; '
        'for name in ' + ' '.join(SERVICES) + '; do '
        f'link={root}/etc/runlevels/default/$name; '
        '[ -L "$link" ] || exit 1; '
        'test "$(readlink "$link")" = /etc/init.d/$name; '
        'done; '
        'printf "LYNX_MAINTENANCE_ROLLBACK_READY boot_id=%s\\n" "$boot_id"'
    )
    os.umask(0o077)
    out = ROOT / 'logs' / f'v46-maintenance-rollback-{time.time_ns()}'
    out.mkdir(mode=0o700)
    report = {'state': 'starting', 'phone_ip': args.ip,
              'mode': 'apply' if args.apply else 'prepare',
              'services': SERVICES, 'v46_init_sha256': init_sha,
              'boot_partition_writes': False, 'service_files_deleted': False,
              'steps': []}

    def step(name, command):
        run = subprocess.run(ssh_command(args.ip, command), capture_output=True, timeout=20)
        (out / f'{name}.stdout').write_bytes(run.stdout)
        (out / f'{name}.stderr').write_bytes(run.stderr)
        report['steps'].append({'name': name, 'exit_code': run.returncode,
                                'stdout_sha256': hashlib.sha256(run.stdout).hexdigest()})
        if run.returncode:
            raise ValueError(f'{name} failed; inspect private streams')
        return run.stdout.decode(errors='replace')

    try:
        output = step('preflight', preflight)
        matched = re.fullmatch(
            r'LYNX_MAINTENANCE_ROLLBACK_READY boot_id=([0-9a-f-]{36})\n?', output)
        if not matched:
            raise ValueError('Rollback preflight marker missing')
        boot_id = matched.group(1)
        report['boot_id'] = boot_id
        if args.apply:
            prepared_path = args.prepared.resolve(strict=True)
            if not prepared_path.is_relative_to(ROOT / 'logs'):
                raise ValueError('Prepared receipt outside Lynx logs')
            prepared = json.loads(prepared_path.read_text())
            if (prepared.get('state') != 'v46-maintenance-rollback-ready' or
                    prepared.get('boot_id') != boot_id or
                    prepared.get('phone_ip') != args.ip or
                    prepared.get('v46_init_sha256') != init_sha):
                raise ValueError('Prepared rollback does not match current V46 boot')
            archive = f'{root}/etc/lynx/maintenance-disabled-{boot_id}'
            command = (
                'set -eu; '
                f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{boot_id}"; '
                f'test ! -e {archive}; '
                f'install -d -m 0700 {archive}; '
                'for name in ' + ' '.join(SERVICES) + '; do '
                f'link={root}/etc/runlevels/default/$name; '
                '[ -L "$link" ] || exit 1; '
                'test "$(readlink "$link")" = /etc/init.d/$name; '
                f'mv "$link" {archive}/$name.default.symlink; '
                'done; '
                'printf LYNX_MAINTENANCE_RUNLEVELS_DISABLED'
            )
            if 'LYNX_MAINTENANCE_RUNLEVELS_DISABLED' not in step('disable_next_boot', command):
                raise ValueError('Rollback completion marker missing')
            report.update(state='v46-maintenance-runlevels-disabled', archive=archive)
        else:
            report['state'] = 'v46-maintenance-rollback-ready'
    except Exception as error:
        report.update(state='failed-or-incomplete', error=str(error))
    report['finished_ns'] = time.time_ns()
    receipt = out / 'result.json'
    receipt.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'state': report['state'], 'result': str(receipt),
                      'boot_id': report.get('boot_id')}))
    if report['state'] not in ('v46-maintenance-rollback-ready',
                               'v46-maintenance-runlevels-disabled'):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
