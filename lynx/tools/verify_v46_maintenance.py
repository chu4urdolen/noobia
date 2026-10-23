"""Verify supervised Lynx maintenance and all prerequisite services."""

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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verification', required=True, type=Path)
    args = parser.parse_args()
    path = args.verification.resolve(strict=True)
    if not path.is_relative_to(ROOT / 'logs'):
        raise ValueError('Verification outside Lynx logs')
    proof = json.loads(path.read_text())
    boot_id, ip = proof['boot_id'], proof['phone_ip']
    if (proof.get('state') != 'v46-autonomous-alpine-pid1-verified' or
            not re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', boot_id) or
            not re.fullmatch(r'192\.168\.100\.[1-9][0-9]?', ip)):
        raise ValueError('V46 same-boot verification missing')
    shas = [hashlib.sha256(x.read_bytes()).hexdigest() for x in (SCRIPT, SERVICE)]
    command = (
        'set -eu; '
        f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{boot_id}"; '
        'test "$(readlink /proc/1/exe)" = /sbin/openrc-init; '
        f'test "$(sha256sum /usr/libexec/lynx-maintenance-watch.sh | cut -c1-64)" = "{shas[0]}"; '
        f'test "$(sha256sum /etc/init.d/lynx-maintenance | cut -c1-64)" = "{shas[1]}"; '
        'test "$(readlink -f /etc/runlevels/default/lynx-maintenance)" = /etc/init.d/lynx-maintenance; '
        'for service in lynx-health lynx-battery-reserve lynx-local-logs lynx-wifi lynx-dropbear lynx-maintenance; do '
        '/sbin/rc-service "$service" status >/dev/null; done; '
        '/bin/sh /usr/libexec/lynx-maintenance-watch.sh --once; '
        'count=0; for d in /sys/class/power_supply/*; do '
        '[ -r "$d/online" ] || continue; test "$(cat "$d/online")" = 0; count=$((count+1)); done; '
        'test "$count" -ge 1; '
        'printf LYNX_MAINTENANCE_VERIFIED'
    )
    argv = ssh_command(ip, command)
    argv[-2:-2] = ['-p', '2222']
    os.umask(0o077)
    out = ROOT / 'logs' / f'v46-maintenance-verify-{time.time_ns()}'
    out.mkdir(mode=0o700)
    report = {'state': 'starting', 'boot_id': boot_id, 'phone_ip': ip,
              'verification': str(path), 'script_sha256': shas[0],
              'service_sha256': shas[1], 'read_only': True}
    try:
        run = subprocess.run(argv, capture_output=True, timeout=20)
        (out / 'stdout').write_bytes(run.stdout)
        (out / 'stderr').write_bytes(run.stderr)
        if (run.returncode or b'LYNX_MAINTENANCE_OK ' not in run.stdout or
                b'LYNX_MAINTENANCE_VERIFIED' not in run.stdout):
            raise ValueError('Maintenance service proof failed')
        report['state'] = 'v46-maintenance-verified'
    except Exception as error:
        report.update(state='failed-or-incomplete', error=str(error))
    report['finished_ns'] = time.time_ns()
    result = out / 'result.json'
    result.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'state': report['state'], 'result': str(result)}))
    if report['state'] != 'v46-maintenance-verified':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
