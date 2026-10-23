"""Read-only proof that Lynx timekeeping and SSH remain healthy."""

import json
import os
from pathlib import Path
import re
import subprocess
import time

from lynx_wifi_v19_contact import ssh_command


ROOT = Path(__file__).resolve().parent.parent
IP = '192.168.100.8'
BOOT_ID = 'f6230cac-8d41-48da-bf28-2700e9ff56f1'
SHA = 'f655adc9f79e9e560d33196894d836a687ee4490f334d83c511c7c4f520241df'


def main():
    os.umask(0o077)
    out = ROOT / 'logs' / f'v46-time-sync-verify-{time.time_ns()}'
    out.mkdir(mode=0o700)
    command = (
        'set -eu; '
        f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{BOOT_ID}"; '
        f'test "$(sha256sum /etc/init.d/lynx-time-sync | cut -c1-64)" = "{SHA}"; '
        'test "$(readlink -f /etc/runlevels/default/lynx-time-sync)" = /etc/init.d/lynx-time-sync; '
        'test ! -e /etc/runlevels/default/chronyd; '
        'test "$(stat -c %a /dev/null)" = 666; '
        'test "$(stat -c %a /dev/random)" = 666; '
        'test "$(stat -c %a /dev/urandom)" = 666; '
        'for s in lynx-health lynx-battery-reserve lynx-wifi lynx-dropbear lynx-time-sync; do '
        '/sbin/rc-service "$s" status >/dev/null; done; '
        'test "$(date -u +%Y)" = 2026; '
        'chronyc tracking; '
        'printf LYNX_TIME_SYNC_VERIFIED'
    )
    argv = ssh_command(IP, command)
    argv[-2:-2] = ['-p', '2222']
    run = subprocess.run(argv, capture_output=True, timeout=20)
    (out / 'stdout').write_bytes(run.stdout)
    (out / 'stderr').write_bytes(run.stderr)
    output = run.stdout.decode(errors='replace')
    match = re.search(r'^Leap status\s*:\s*(.+)$', output, re.M)
    state = ('v46-time-sync-verified' if run.returncode == 0 and
             'LYNX_TIME_SYNC_VERIFIED' in output and match and
             match.group(1).strip() == 'Normal' else 'failed-or-incomplete')
    result = out / 'result.json'
    result.write_text(json.dumps({'state': state, 'boot_id': BOOT_ID,
                                  'phone_ip': IP, 'time_service_sha256': SHA,
                                  'ntp_leap_status': match.group(1).strip() if match else None,
                                  'exit_code': run.returncode, 'phone_writes': False},
                                 indent=2) + '\n')
    print(json.dumps({'state': state, 'result': str(result)}))
    if state != 'v46-time-sync-verified':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
