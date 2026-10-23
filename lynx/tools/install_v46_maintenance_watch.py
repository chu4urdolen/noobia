"""Install Lynx's supervised userland maintenance watcher over Alpine SSH."""

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
SCRIPT = ROOT / 'linux-port/lynx-maintenance-watch.sh'
SERVICE = ROOT / 'linux-port/openrc-lynx-maintenance'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verification', required=True, type=Path)
    parser.add_argument('--reserve-verification', required=True, type=Path)
    parser.add_argument('--logs-verification', required=True, type=Path)
    args = parser.parse_args()
    paths = [x.resolve(strict=True) for x in
             (args.verification, args.reserve_verification, args.logs_verification)]
    if any(not x.is_relative_to(ROOT / 'logs') for x in paths):
        raise ValueError('Verification outside Lynx logs')
    boot, reserve, logs = [json.loads(x.read_text()) for x in paths]
    boot_id, ip = boot['boot_id'], boot['phone_ip']
    if (boot.get('state') != 'v46-autonomous-alpine-pid1-verified' or
            reserve.get('state') != 'v46-battery-reserve-verified' or
            logs.get('state') != 'v46-local-logs-verified' or
            any(x.get('boot_id') != boot_id or x.get('phone_ip') != ip
                for x in (reserve, logs)) or
            not re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', boot_id) or
            not re.fullmatch(r'192\.168\.100\.[1-9][0-9]?', ip)):
        raise ValueError('Same-boot prerequisite receipts missing')
    for path in (SCRIPT, SERVICE):
        subprocess.run(['/bin/sh', '-n', str(path)], check=True)
    os.umask(0o077)
    out = ROOT / 'logs' / f'v46-maintenance-install-{time.time_ns()}'
    out.mkdir(mode=0o700)
    report = {'state': 'starting', 'boot_id': boot_id, 'phone_ip': ip,
              'verifications': [str(x) for x in paths],
              'script_sha256': digest(SCRIPT), 'service_sha256': digest(SERVICE),
              'boot_partition_writes': False, 'charging_changes': False,
              'steps': []}

    def step(name, command, data=None, timeout=20):
        argv = ssh_command(ip, command)
        argv[-2:-2] = ['-p', '2222']
        run = subprocess.run(argv, input=data, capture_output=True, timeout=timeout)
        (out / f'{name}.stdout').write_bytes(run.stdout)
        (out / f'{name}.stderr').write_bytes(run.stderr)
        report['steps'].append({'name': name, 'exit_code': run.returncode,
                                'stdout_sha256': hashlib.sha256(run.stdout).hexdigest()})
        if run.returncode:
            raise ValueError(f'{name} failed; inspect private streams')
        return run.stdout.decode(errors='replace')

    try:
        preflight = (
            'set -eu; '
            f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{boot_id}"; '
            'test "$(readlink /proc/1/exe)" = /sbin/openrc-init; '
            '/sbin/rc-service lynx-health status >/dev/null; '
            '/sbin/rc-service lynx-battery-reserve status >/dev/null; '
            '/sbin/rc-service lynx-local-logs status >/dev/null; '
            '/sbin/rc-service lynx-wifi status >/dev/null; '
            '/sbin/rc-service lynx-dropbear status >/dev/null; '
            'test ! -e /etc/init.d/lynx-maintenance; '
            'test ! -e /usr/libexec/lynx-maintenance-watch.sh; '
            'test -w /usr/libexec; '
            'printf LYNX_MAINTENANCE_PREFLIGHT_OK'
        )
        if 'LYNX_MAINTENANCE_PREFLIGHT_OK' not in step('preflight', preflight):
            raise ValueError('Preflight marker missing')
        step('stage_script', 'cat > /run/lynx/maintenance-watch.stage', data=SCRIPT.read_bytes())
        step('stage_service', 'cat > /run/lynx/maintenance-openrc.stage', data=SERVICE.read_bytes())
        dry = (
            'set -eu; '
            f'test "$(sha256sum /run/lynx/maintenance-watch.stage | cut -c1-64)" = "{digest(SCRIPT)}"; '
            f'test "$(sha256sum /run/lynx/maintenance-openrc.stage | cut -c1-64)" = "{digest(SERVICE)}"; '
            '/bin/sh -n /run/lynx/maintenance-watch.stage; '
            '/bin/sh /run/lynx/maintenance-watch.stage --once'
        )
        if 'LYNX_MAINTENANCE_OK' not in step('on_phone_once', dry):
            raise ValueError('On-phone read-only maintenance check missing')
        install = (
            'set -eu; '
            f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{boot_id}"; '
            'install -m 0755 /run/lynx/maintenance-watch.stage /usr/libexec/lynx-maintenance-watch.sh.new; '
            'install -m 0755 /run/lynx/maintenance-openrc.stage /etc/init.d/lynx-maintenance.new; '
            'mv /usr/libexec/lynx-maintenance-watch.sh.new /usr/libexec/lynx-maintenance-watch.sh; '
            'mv /etc/init.d/lynx-maintenance.new /etc/init.d/lynx-maintenance; '
            '/sbin/rc-update add lynx-maintenance default; '
            '/sbin/rc-service lynx-maintenance start; '
            '/sbin/rc-service lynx-maintenance status; '
            'test -L /etc/runlevels/default/lynx-maintenance; '
            'printf LYNX_MAINTENANCE_INSTALLED'
        )
        if 'LYNX_MAINTENANCE_INSTALLED' not in step('install', install, timeout=40):
            raise ValueError('Install marker missing')
        report['state'] = 'v46-maintenance-installed-and-running'
    except Exception as error:
        report.update(state='failed-or-incomplete', error=str(error))
    report['finished_ns'] = time.time_ns()
    receipt = out / 'result.json'
    receipt.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'state': report['state'], 'result': str(receipt)}))
    if report['state'] != 'v46-maintenance-installed-and-running':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
