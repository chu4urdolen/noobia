"""Let the maintenance supervisor start after optional services fail."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time

from lynx_wifi_v19_contact import ssh_command

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / 'linux-port/openrc-lynx-maintenance'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verification', required=True, type=Path)
    parser.add_argument('--old-install', required=True, type=Path)
    args = parser.parse_args()
    paths = [x.resolve(strict=True) for x in (args.verification, args.old_install)]
    if any(not x.is_relative_to(ROOT / 'logs') for x in paths):
        raise ValueError('Receipt outside Lynx logs')
    boot, old = [json.loads(x.read_text()) for x in paths]
    boot_id, ip = boot['boot_id'], boot['phone_ip']
    if (boot.get('state') != 'v46-autonomous-alpine-pid1-verified' or
            old.get('state') != 'v46-maintenance-installed-and-running' or
            old.get('phone_ip') != ip or old.get('boot_id') == boot_id or
            not re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', boot_id) or
            not re.fullmatch(r'192\.168\.100\.[1-9][0-9]?', ip)):
        raise ValueError('Exact V46 new boot and prior maintenance receipt missing')
    subprocess.run(['/bin/sh', '-n', str(SOURCE)], check=True)
    data = SOURCE.read_bytes()
    new_sha = hashlib.sha256(data).hexdigest()
    old_sha = old['service_sha256']
    if new_sha == old_sha:
        raise ValueError('Maintenance service source unchanged')
    os.umask(0o077)
    out = ROOT / 'logs' / f'v46-maintenance-dependencies-{time.time_ns()}'
    out.mkdir(mode=0o700)
    report = {'state': 'starting', 'boot_id': boot_id, 'phone_ip': ip,
              'verification': str(paths[0]), 'old_install': str(paths[1]),
              'old_sha256': old_sha, 'new_sha256': new_sha,
              'boot_partition_writes': False, 'running_process_restart': False,
              'steps': []}

    def step(name, command, payload=None):
        argv = ssh_command(ip, command)
        argv[-2:-2] = ['-p', '2222']
        run = subprocess.run(argv, input=payload, capture_output=True, timeout=20)
        (out / f'{name}.stdout').write_bytes(run.stdout)
        (out / f'{name}.stderr').write_bytes(run.stderr)
        report['steps'].append({'name': name, 'exit_code': run.returncode,
                                'stdout_sha256': hashlib.sha256(run.stdout).hexdigest()})
        if run.returncode:
            raise ValueError(f'{name} failed; see private streams')
        return run.stdout.decode(errors='replace')

    target = '/etc/init.d/lynx-maintenance'
    backup = '/run/lynx/lynx-maintenance.service.old'
    try:
        preflight = (
            'set -eu; '
            f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{boot_id}"; '
            'test "$(readlink /proc/1/exe)" = /sbin/openrc-init; '
            f'test "$(sha256sum {target} | cut -c1-64)" = "{old_sha}"; '
            'for service in lynx-health lynx-battery-reserve lynx-local-logs lynx-maintenance; do '
            '/sbin/rc-service "$service" status >/dev/null; done; '
            f'test ! -e {backup}; '
            'printf LYNX_DEPENDENCY_UPDATE_READY'
        )
        if 'LYNX_DEPENDENCY_UPDATE_READY' not in step('preflight', preflight):
            raise ValueError('Dependency preflight marker missing')
        step('stage', 'cat > /run/lynx/lynx-maintenance.service.new', payload=data)
        update = (
            'set -eu; '
            f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{boot_id}"; '
            f'test "$(sha256sum /run/lynx/lynx-maintenance.service.new | cut -c1-64)" = "{new_sha}"; '
            f'cp -p {target} {backup}; '
            f'test "$(sha256sum {backup} | cut -c1-64)" = "{old_sha}"; '
            f'install -m 0755 /run/lynx/lynx-maintenance.service.new {target}.new; '
            f'mv {target}.new {target}; '
            '/sbin/rc-service lynx-maintenance status >/dev/null; '
            f'test "$(sha256sum {target} | cut -c1-64)" = "{new_sha}"; '
            'printf LYNX_DEPENDENCIES_UPDATED'
        )
        if 'LYNX_DEPENDENCIES_UPDATED' not in step('update', update):
            raise ValueError('Dependency update marker missing')
        report['state'] = 'v46-maintenance-dependencies-updated'
    except Exception as error:
        report.update(state='failed-or-incomplete', error=str(error))
        try:
            restore = (
                'set -eu; '
                f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{boot_id}"; '
                f'test "$(sha256sum {backup} | cut -c1-64)" = "{old_sha}"; '
                f'cp -p {backup} {target}.restore; '
                f'mv {target}.restore {target}; '
                '/sbin/rc-service lynx-maintenance status >/dev/null; '
                'printf LYNX_OLD_MAINTENANCE_RESTORED'
            )
            report['old_service_restored'] = ('LYNX_OLD_MAINTENANCE_RESTORED' in
                                              step('restore_old', restore))
        except Exception as fallback_error:
            report['fallback_error'] = str(fallback_error)
    report['finished_ns'] = time.time_ns()
    result = out / 'result.json'
    result.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'state': report['state'], 'result': str(result),
                      'old_service_restored': report.get('old_service_restored')}))
    if report['state'] != 'v46-maintenance-dependencies-updated':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
