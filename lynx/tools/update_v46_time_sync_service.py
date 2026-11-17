"""Add persistent device-node permissions to Lynx's live time service."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from lynx_wifi_v19_contact import ssh_command


ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / 'linux-port/openrc-lynx-time-sync'
IP = '192.168.100.8'
BOOT_ID = 'f6230cac-8d41-48da-bf28-2700e9ff56f1'
OLD_SHA = 'e9235837ab4d9a35b954f5fac9b70210418ecb1b304d20ba2ecaaaa5f28e1b91'


def main():
    subprocess.run(['/bin/sh', '-n', str(SOURCE)], check=True)
    data = SOURCE.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    os.umask(0o077)
    out = ROOT / 'logs' / f'v46-time-sync-update-{time.time_ns()}'
    out.mkdir(mode=0o700)
    report = {'state': 'starting', 'boot_id': BOOT_ID, 'phone_ip': IP,
              'old_sha256': OLD_SHA, 'new_sha256': digest,
              'boot_partition_writes': False, 'steps': []}

    def step(name, command, payload=None, timeout=25):
        argv = ssh_command(IP, command)
        argv[-2:-2] = ['-p', '2222']
        run = subprocess.run(argv, input=payload, capture_output=True, timeout=timeout)
        (out / f'{name}.stdout').write_bytes(run.stdout)
        (out / f'{name}.stderr').write_bytes(run.stderr)
        report['steps'].append({'name': name, 'exit_code': run.returncode})
        if run.returncode:
            raise RuntimeError(f'{name} failed; see saved streams')
        return run.stdout.decode(errors='replace')

    target = '/etc/init.d/lynx-time-sync'
    backup = '/root/lynx-rescue/lynx-time-sync-initial-v46.sh'
    try:
        step('preflight',
             'set -eu; '
             f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{BOOT_ID}"; '
             f'test "$(sha256sum {target} | cut -c1-64)" = "{OLD_SHA}"; '
             f'test ! -e {backup}; '
             '/sbin/rc-service lynx-time-sync status >/dev/null; '
             '/sbin/rc-service lynx-health status >/dev/null; '
             '/sbin/rc-service lynx-wifi status >/dev/null; '
             'test "$(date -u +%Y)" = 2026; '
             'printf LYNX_TIME_UPDATE_PREFLIGHT')
        step('stage', 'cat > /run/lynx/lynx-time-sync.updated', payload=data)
        step('update',
             'set -eu; '
             f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{BOOT_ID}"; '
             f'test "$(sha256sum /run/lynx/lynx-time-sync.updated | cut -c1-64)" = "{digest}"; '
             'install -d -m 0700 /root/lynx-rescue; '
             f'cp -p {target} {backup}; '
             f'install -m 0755 /run/lynx/lynx-time-sync.updated {target}.new; '
             f'mv {target}.new {target}; '
             '/sbin/rc-service lynx-time-sync restart; '
             '/sbin/rc-service lynx-time-sync status; '
             'printf LYNX_TIME_SERVICE_UPDATED', timeout=35)
        proof = step('verify',
                     'set -eu; '
                     f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{BOOT_ID}"; '
                     f'test "$(sha256sum {target} | cut -c1-64)" = "{digest}"; '
                     f'test "$(sha256sum {backup} | cut -c1-64)" = "{OLD_SHA}"; '
                     'test "$(stat -c %a /dev/urandom)" = 666; '
                     'test "$(stat -c %a /dev/null)" = 666; '
                     'test "$(date -u +%Y)" = 2026; '
                     '/sbin/rc-service lynx-time-sync status; '
                     'chronyc tracking; '
                     'printf LYNX_TIME_UPDATE_VERIFIED')
        if 'LYNX_TIME_UPDATE_VERIFIED' not in proof:
            raise RuntimeError('Time update proof absent')
        report['state'] = 'v46-time-sync-service-updated-and-running'
    except Exception as exc:
        report.update(state='failed-or-incomplete', error=str(exc))
    report['finished_ns'] = time.time_ns()
    result = out / 'result.json'
    result.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'state': report['state'], 'result': str(result)}))
    if report['state'] != 'v46-time-sync-service-updated-and-running':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
