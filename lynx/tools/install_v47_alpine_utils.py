"""Install small signed Alpine utilities on a verified, healthy V47 boot."""

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time

from lynx_wifi_v19_contact import ssh_command


ROOT = Path(__file__).resolve().parent.parent
IP = '192.168.100.8'
BOOT_ID = '9054078d-aafa-4abf-9600-5c70f8234360'
INIT_SHA = 'ebc6bb746aaf710d915c47036f92ce0c4ed23a185dfb5349b90e654bab7ba4ae'
PACKAGES = ('curl', 'jq', 'tmux', 'rsync')


def main():
    os.umask(0o077)
    out = ROOT / 'logs' / f'v47-alpine-utils-{time.time_ns()}'
    out.mkdir(mode=0o700)
    report = {'state': 'starting', 'boot_id': BOOT_ID, 'packages': PACKAGES,
              'boot_partition_writes': False, 'steps': []}

    def step(name, command, timeout=40, port=2222):
        argv = ssh_command(IP, command)
        argv[-2:-2] = ['-p', str(port)]
        run = subprocess.run(argv, capture_output=True, timeout=timeout)
        (out / f'{name}.stdout').write_bytes(run.stdout)
        (out / f'{name}.stderr').write_bytes(run.stderr)
        report['steps'].append({
            'name': name, 'exit_code': run.returncode,
            'stdout_sha256': hashlib.sha256(run.stdout).hexdigest(),
            'stderr_sha256': hashlib.sha256(run.stderr).hexdigest()})
        if run.returncode:
            raise RuntimeError(f'{name} failed; inspect saved streams')
        return run.stdout.decode(errors='replace')

    try:
        step('rescue_identity',
             'set -eu; '
             f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{BOOT_ID}"; '
             f'test "$(sha256sum /init | cut -c1-64)" = "{INIT_SHA}"; '
             'printf LYNX_V47_RESCUE_VERIFIED', port=22)
        ready = step('preflight',
            'set -eu; '
            f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{BOOT_ID}"; '
            'test "$(readlink /proc/1/exe)" = /sbin/openrc-init; '
            'test "$(cat /etc/alpine-release)" = 3.24.2; '
            'test "$(awk \'$2=="/" {print $3; exit}\' /proc/mounts)" = ext4; '
            'test "$(df -Pm / | awk \'NR==2 {print $4}\')" -ge 750; '
            'test "$(date -u +%Y)" = 2026; '
            'chronyc tracking | grep -q "Leap status *: Normal"; '
            'for s in lynx-health lynx-battery-reserve lynx-local-logs '
            'lynx-wifi lynx-dropbear lynx-maintenance lynx-time-sync '
            'lynx-power-history; do /sbin/rc-service "$s" status >/dev/null; done; '
            'sample=$(cat /sys/bus/i2c/devices/7-0055/battery_snapshot); '
            'printf "%s\n" "$sample" | grep -qx capacity_error=0; '
            'printf "%s\n" "$sample" | grep -qx temperature_error=0; '
            'capacity=$(printf "%s\n" "$sample" | sed -n "s/^capacity_percent=//p"); '
            'temp=$(printf "%s\n" "$sample" | sed -n "s/^temperature_millidegrees_celsius=//p"); '
            'case "$capacity:$temp" in *[!0-9:]*|::*|*::*) exit 1;; esac; '
            'test "$capacity" -ge 70; test "$temp" -ge 10000; '
            'test "$temp" -lt 35000; '
            'printf "LYNX_UTILS_READY capacity=%s temp_mC=%s\n" "$capacity" "$temp"')
        if not re.fullmatch(r'LYNX_UTILS_READY capacity=\d+ temp_mC=\d+\n', ready):
            raise RuntimeError('preflight marker absent')
        report['battery_preflight'] = ready.strip()
        step('simulate_fresh', 'apk add --no-cache --simulate ' + ' '.join(PACKAGES), timeout=60)
        step('install', 'apk add --no-cache ' + ' '.join(PACKAGES), timeout=180)
        proof = step('verify',
            'set -eu; '
            f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{BOOT_ID}"; '
            'for p in curl jq tmux rsync; do apk info -e "$p" >/dev/null; done; '
            'test "$(df -Pm / | awk \'NR==2 {print $4}\')" -ge 750; '
            'for s in lynx-health lynx-battery-reserve lynx-local-logs '
            'lynx-wifi lynx-dropbear lynx-maintenance lynx-time-sync '
            'lynx-power-history; do /sbin/rc-service "$s" status >/dev/null; done; '
            'curl --version | head -n 1; jq --version; tmux -V; '
            'rsync --version | head -n 1; '
            'printf LYNX_UTILS_VERIFIED')
        if 'LYNX_UTILS_VERIFIED' not in proof:
            raise RuntimeError('verification marker absent')
        report['state'] = 'v47-alpine-utils-installed-and-verified'
    except Exception as exc:
        report.update(state='failed-or-incomplete', error=str(exc))
    report['finished_ns'] = time.time_ns()
    result = out / 'result.json'
    result.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'state': report['state'], 'result': str(result)}))
    if report['state'] != 'v47-alpine-utils-installed-and-verified':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
