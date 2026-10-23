"""Independently verify the live battery reserve guard on Alpine SSH."""

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
SCRIPT = ROOT / 'linux-port/lynx-battery-reserve.sh'
SERVICE = ROOT / 'linux-port/openrc-lynx-battery-reserve'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verification', required=True, type=Path)
    parser.add_argument('--charging-trial', action='store_true',
                        help='Require positive net gauge current at or below reserve threshold')
    args = parser.parse_args()
    proof_path = args.verification.resolve(strict=True)
    if not proof_path.is_relative_to(ROOT / 'logs'):
        raise ValueError('Verification outside Lynx logs')
    proof = json.loads(proof_path.read_text())
    boot_id, ip = proof['boot_id'], proof['phone_ip']
    if (proof.get('state') != 'v46-autonomous-alpine-pid1-verified' or
            not re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', boot_id) or
            not re.fullmatch(r'192\.168\.100\.[1-9][0-9]?', ip)):
        raise ValueError('V46 same-boot verification missing')
    script_sha = hashlib.sha256(SCRIPT.read_bytes()).hexdigest()
    service_sha = hashlib.sha256(SERVICE.read_bytes()).hexdigest()
    command = (
        'set -eu; '
        f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{boot_id}"; '
        'test "$(readlink /proc/1/exe)" = /sbin/openrc-init; '
        f'test "$(sha256sum /usr/libexec/lynx-battery-reserve.sh | cut -c1-64)" = "{script_sha}"; '
        f'test "$(sha256sum /etc/init.d/lynx-battery-reserve | cut -c1-64)" = "{service_sha}"; '
        'test -L /etc/runlevels/default/lynx-battery-reserve; '
        'test "$(readlink -f /etc/runlevels/default/lynx-battery-reserve)" = /etc/init.d/lynx-battery-reserve; '
        '/sbin/rc-service lynx-battery-reserve status >/dev/null; '
        '/sbin/rc-service lynx-health status >/dev/null; '
        'pid=$(cat /run/lynx/battery-reserve/pid); '
        'case "$pid" in ""|*[!0-9]*) exit 1;; esac; '
        'kill -0 "$pid"; '
        'tr "\\000" "\\n" < /proc/$pid/cmdline | grep -Fxq /usr/libexec/lynx-battery-reserve.sh; '
        '/bin/sh /usr/libexec/lynx-battery-reserve.sh --once; '
        'count=0; for d in /sys/class/power_supply/*; do '
        '[ -r "$d/online" ] || continue; '
        'test "$(cat "$d/online")" = 0; count=$((count+1)); done; '
        'test "$count" -ge 1; '
        'printf LYNX_V46_RESERVE_VERIFIED'
    )
    argv = ssh_command(ip, command)
    argv[-2:-2] = ['-p', '2222']
    os.umask(0o077)
    out = ROOT / 'logs' / f'v46-battery-reserve-verify-{time.time_ns()}'
    out.mkdir(mode=0o700)
    receipt = {'state': 'starting', 'boot_id': boot_id, 'phone_ip': ip,
               'verification': str(proof_path), 'script_sha256': script_sha,
               'service_sha256': service_sha, 'read_only': True,
               'charging_trial': args.charging_trial}
    try:
        run = subprocess.run(argv, capture_output=True, timeout=20)
        (out / 'stdout').write_bytes(run.stdout)
        (out / 'stderr').write_bytes(run.stderr)
        data = run.stdout.decode(errors='replace')
        if run.returncode or 'LYNX_V46_RESERVE_VERIFIED' not in data:
            raise ValueError('Reserve service proof failed')
        capacity = re.search(r'capacity_percent=(\d+)', data)
        current = re.search(r'current_ma=(-?\d+)', data)
        temperature = re.search(r'temperature_millidegrees=(\d+)', data)
        if not capacity or not current or not temperature:
            raise ValueError('Battery reserve telemetry missing')
        value, amps, degrees = (int(capacity.group(1)), int(current.group(1)),
                                int(temperature.group(1)))
        if args.charging_trial:
            if not 11 <= value <= 20 or amps < 50 or degrees >= 40000:
                raise ValueError('Charging hold not proven at reserve threshold')
        elif not 21 <= value <= 100:
            raise ValueError('Battery reserve already low or invalid')
        receipt.update(state='v46-battery-reserve-verified',
                       capacity_percent=value, current_ma=amps,
                       temperature_millidegrees=degrees)
    except Exception as error:
        receipt.update(state='failed-or-incomplete', error=str(error))
    receipt['finished_ns'] = time.time_ns()
    result = out / 'result.json'
    result.write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps({'state': receipt['state'], 'result': str(result),
                      'capacity_percent': receipt.get('capacity_percent')}))
    if receipt['state'] != 'v46-battery-reserve-verified':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
