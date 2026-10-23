"""Install bounded local syslog/klog on a verified V46 Alpine boot."""

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
SOURCE = ROOT / 'linux-port/openrc-lynx-local-logs'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verification', required=True, type=Path)
    parser.add_argument('--reserve-verification', required=True, type=Path)
    args = parser.parse_args()
    path = args.verification.resolve(strict=True)
    reserve_path = args.reserve_verification.resolve(strict=True)
    for candidate in (path, reserve_path):
        if not candidate.is_relative_to(ROOT / 'logs'):
            raise ValueError('Verification outside Lynx logs')
    proof, reserve = json.loads(path.read_text()), json.loads(reserve_path.read_text())
    boot_id, ip = proof['boot_id'], proof['phone_ip']
    if (proof.get('state') != 'v46-autonomous-alpine-pid1-verified' or
            reserve.get('state') != 'v46-battery-reserve-verified' or
            reserve.get('boot_id') != boot_id or reserve.get('phone_ip') != ip or
            not re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', boot_id) or
            not re.fullmatch(r'192\.168\.100\.[1-9][0-9]?', ip)):
        raise ValueError('Same-boot Alpine and reserve verification missing')
    subprocess.run(['/bin/sh', '-n', str(SOURCE)], check=True)
    source = SOURCE.read_bytes()
    digest = hashlib.sha256(source).hexdigest()
    if b'-R ' in source or b'--remote' in source:
        raise ValueError('Network forwarding option found in local logger')
    os.umask(0o077)
    out = ROOT / 'logs' / f'v46-local-logs-install-{time.time_ns()}'
    out.mkdir(mode=0o700)
    report = {'state': 'starting', 'boot_id': boot_id, 'phone_ip': ip,
              'verification': str(path), 'reserve_verification': str(reserve_path),
              'service_sha256': digest, 'boot_partition_writes': False,
              'network_forwarding': False, 'steps': []}

    def run_step(name, command, data=None, timeout=20):
        argv = ssh_command(ip, command)
        argv[-2:-2] = ['-p', '2222']
        result = subprocess.run(argv, input=data, capture_output=True, timeout=timeout)
        (out / f'{name}.stdout').write_bytes(result.stdout)
        (out / f'{name}.stderr').write_bytes(result.stderr)
        report['steps'].append({'name': name, 'exit_code': result.returncode,
                                'stdout_sha256': hashlib.sha256(result.stdout).hexdigest()})
        if result.returncode:
            raise ValueError(f'{name} failed; inspect private streams')
        return result.stdout.decode(errors='replace')

    try:
        preflight = (
            'set -eu; '
            f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{boot_id}"; '
            'test "$(readlink /proc/1/exe)" = /sbin/openrc-init; '
            'test "$(awk \'$2=="/" {print $3; exit}\' /proc/mounts)" = ext4; '
            '/sbin/rc-service lynx-health status >/dev/null; '
            '/sbin/rc-service lynx-battery-reserve status >/dev/null; '
            'test -w /var/log; '
            'test ! -e /etc/init.d/lynx-local-logs; '
            'test ! -e /run/lynx/lynx-syslogd.pid; '
            'test ! -e /run/lynx/lynx-klogd.pid; '
            '! pgrep -x syslogd >/dev/null; '
            '! pgrep -x klogd >/dev/null; '
            'printf LYNX_LOCAL_LOGS_PREFLIGHT_OK'
        )
        if 'LYNX_LOCAL_LOGS_PREFLIGHT_OK' not in run_step('preflight', preflight):
            raise ValueError('Preflight marker missing')
        run_step('stage', 'cat > /run/lynx/lynx-local-logs.stage', data=source)
        install = (
            'set -eu; '
            f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{boot_id}"; '
            f'test "$(sha256sum /run/lynx/lynx-local-logs.stage | cut -c1-64)" = "{digest}"; '
            'install -m 0755 /run/lynx/lynx-local-logs.stage /etc/init.d/lynx-local-logs.new; '
            'mv /etc/init.d/lynx-local-logs.new /etc/init.d/lynx-local-logs; '
            '/sbin/rc-update add lynx-local-logs default; '
            '/sbin/rc-service lynx-local-logs start; '
            '/sbin/rc-service lynx-local-logs status; '
            'test -s /var/log/lynx/messages; '
            'test -L /etc/runlevels/default/lynx-local-logs; '
            'printf LYNX_LOCAL_LOGS_INSTALLED'
        )
        if 'LYNX_LOCAL_LOGS_INSTALLED' not in run_step('install', install, timeout=35):
            raise ValueError('Install marker missing')
        report['state'] = 'v46-local-logs-installed-and-running'
    except Exception as error:
        report.update(state='failed-or-incomplete', error=str(error))
    report['finished_ns'] = time.time_ns()
    result_path = out / 'result.json'
    result_path.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'state': report['state'], 'result': str(result_path)}))
    if report['state'] != 'v46-local-logs-installed-and-running':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
