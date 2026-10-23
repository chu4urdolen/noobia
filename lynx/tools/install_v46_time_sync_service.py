"""Install a Lynx Chrony OpenRC service without Alpine's generic network dependency."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from lynx_wifi_v19_contact import ssh_command


ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / 'linux-port/openrc-lynx-time-sync'
BOOT_ID = 'f6230cac-8d41-48da-bf28-2700e9ff56f1'
IP = '192.168.100.8'


def main():
    subprocess.run(['/bin/sh', '-n', str(SOURCE)], check=True)
    payload = SOURCE.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    os.umask(0o077)
    out = ROOT / 'logs' / f'v46-time-sync-service-{time.time_ns()}'
    out.mkdir(mode=0o700)
    report = {'state': 'starting', 'phone_ip': IP, 'boot_id': BOOT_ID,
              'source_sha256': digest, 'boot_partition_writes': False,
              'steps': []}

    def step(name, command, data=None, timeout=25):
        argv = ssh_command(IP, command)
        argv[-2:-2] = ['-p', '2222']
        run = subprocess.run(argv, input=data, capture_output=True, timeout=timeout)
        (out / f'{name}.stdout').write_bytes(run.stdout)
        (out / f'{name}.stderr').write_bytes(run.stderr)
        report['steps'].append({'name': name, 'exit_code': run.returncode,
                                'stdout_sha256': hashlib.sha256(run.stdout).hexdigest()})
        if run.returncode:
            raise RuntimeError(f'{name} failed; see private streams')
        return run.stdout.decode(errors='replace')

    target = '/etc/init.d/lynx-time-sync'
    try:
        step('preflight',
             'set -eu; '
             f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{BOOT_ID}"; '
             'test "$(date -u +%Y)" = 2026; '
             'test "$(readlink /proc/1/exe)" = /sbin/openrc-init; '
             'apk info -e chrony >/dev/null; '
             '/sbin/rc-service lynx-health status >/dev/null; '
             '/sbin/rc-service lynx-wifi status >/dev/null; '
             '/sbin/rc-service lynx-dropbear status >/dev/null; '
             'test ! -e /etc/runlevels/default/chronyd; '
             'test ! -e /etc/runlevels/default/lynx-time-sync; '
             f'test ! -e {target}; '
             'test "$(df -Pm / | awk \'NR==2 {print $4}\')" -ge 500; '
             'printf LYNX_TIME_SERVICE_PREFLIGHT')
        step('stage', 'cat > /run/lynx/lynx-time-sync.new', data=payload)
        step('install',
             'set -eu; '
             f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{BOOT_ID}"; '
             f'test "$(sha256sum /run/lynx/lynx-time-sync.new | cut -c1-64)" = "{digest}"; '
             f'install -m 0755 /run/lynx/lynx-time-sync.new {target}; '
             '/sbin/rc-update add lynx-time-sync default; '
             '/sbin/rc-service lynx-time-sync start; '
             '/sbin/rc-service lynx-time-sync status; '
             'printf LYNX_TIME_SERVICE_STARTED', timeout=35)
        proof = step('verify',
                     'set -eu; '
                     f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{BOOT_ID}"; '
                     f'test "$(sha256sum {target} | cut -c1-64)" = "{digest}"; '
                     f'test "$(readlink -f /etc/runlevels/default/lynx-time-sync)" = "{target}"; '
                     'test "$(date -u +%Y)" = 2026; '
                     '/sbin/rc-service lynx-time-sync status; '
                     '/sbin/rc-service lynx-wifi status; '
                     '/sbin/rc-service lynx-dropbear status; '
                     'chronyc tracking; '
                     'printf LYNX_TIME_SERVICE_VERIFIED')
        if 'LYNX_TIME_SERVICE_VERIFIED' not in proof:
            raise RuntimeError('Time service proof absent')
        report['state'] = 'v46-time-sync-service-installed-and-running'
    except Exception as exc:
        report.update(state='failed-or-incomplete', error=str(exc))
    report['finished_ns'] = time.time_ns()
    result = out / 'result.json'
    result.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'state': report['state'], 'result': str(result)}))
    if report['state'] != 'v46-time-sync-service-installed-and-running':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
