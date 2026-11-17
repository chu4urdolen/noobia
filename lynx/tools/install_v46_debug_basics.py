"""Install basic Alpine diagnostics on a verified live Lynx boot."""

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
PACKAGES = ('strace', 'lsof', 'iw')
BOOT_ID = 'f6230cac-8d41-48da-bf28-2700e9ff56f1'


def main():
    os.umask(0o077)
    out = ROOT / 'logs' / f'v46-debug-basics-{time.time_ns()}'
    out.mkdir(mode=0o700)
    report = {'state': 'starting', 'phone_ip': IP, 'boot_id': BOOT_ID,
              'packages': PACKAGES, 'boot_partition_writes': False,
              'commands': []}

    def step(name, command, timeout=25):
        argv = ssh_command(IP, command)
        argv[-2:-2] = ['-p', '2222']
        run = subprocess.run(argv, capture_output=True, timeout=timeout)
        (out / f'{name}.stdout').write_bytes(run.stdout)
        (out / f'{name}.stderr').write_bytes(run.stderr)
        report['commands'].append({'name': name, 'exit_code': run.returncode,
                                   'stdout_sha256': hashlib.sha256(run.stdout).hexdigest(),
                                   'stderr_sha256': hashlib.sha256(run.stderr).hexdigest()})
        if run.returncode:
            raise RuntimeError(f'{name} failed; see saved streams')
        return run.stdout.decode(errors='replace')

    try:
        preflight = (
            'set -eu; '
            f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{BOOT_ID}"; '
            'test "$(readlink /proc/1/exe)" = /sbin/openrc-init; '
            'test "$(awk \'$2=="/" {print $3; exit}\' /proc/mounts)" = ext4; '
            'for service in lynx-health lynx-battery-reserve lynx-local-logs lynx-maintenance lynx-wifi lynx-dropbear; do '
            '/sbin/rc-service "$service" status >/dev/null; done; '
            'sample=$(cat /sys/bus/i2c/devices/7-0055/battery_snapshot); '
            'printf "%s\\n" "$sample" | grep -qx capacity_error=0; '
            'printf "%s\\n" "$sample" | grep -qx temperature_error=0; '
            'capacity=$(printf "%s\\n" "$sample" | sed -n "s/^capacity_percent=//p"); '
            'temp=$(printf "%s\\n" "$sample" | sed -n "s/^temperature_millidegrees_celsius=//p"); '
            'case "$capacity:$temp" in *[!0-9:]*|::*|*::*) exit 1;; esac; '
            'test "$capacity" -ge 50; test "$temp" -ge 10000; test "$temp" -lt 35000; '
            'test "$(df -Pm / | awk \'NR==2 {print $4}\')" -ge 500; '
            'test "$(cat /etc/alpine-release)" = 3.24.2; '
            'test "$(wc -l < /etc/apk/repositories)" -eq 2; '
            'grep -qx https://dl-cdn.alpinelinux.org/alpine/v3.24/main /etc/apk/repositories; '
            'grep -qx https://dl-cdn.alpinelinux.org/alpine/v3.24/community /etc/apk/repositories; '
            'printf "LYNX_DEBUG_PREFLIGHT capacity=%s temp_mC=%s\\n" "$capacity" "$temp"'
        )
        result = step('preflight', preflight)
        if not re.fullmatch(r'LYNX_DEBUG_PREFLIGHT capacity=\d+ temp_mC=\d+\n', result):
            raise RuntimeError('Preflight marker absent')
        report['battery_preflight'] = result.strip()
        step('simulate', 'apk add --simulate strace lsof iw', timeout=35)
        step('install', 'apk add --no-cache strace lsof iw', timeout=150)
        proof = step('verify',
                     'set -eu; '
                     f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{BOOT_ID}"; '
                     'for package in strace lsof iw; do apk info -e "$package" >/dev/null; done; '
                     'test -x /usr/bin/strace; test -x /usr/bin/lsof; test -x /usr/sbin/iw; '
                     'strace -V | head -n 1; iw --version; '
                     'printf LYNX_DEBUG_BASICS_VERIFIED', timeout=25)
        if 'LYNX_DEBUG_BASICS_VERIFIED' not in proof:
            raise RuntimeError('Verification marker absent')
        report['state'] = 'v46-alpine-debug-basics-installed-and-verified'
    except Exception as exc:
        report.update(state='failed-or-incomplete', error=str(exc))
    report['finished_ns'] = time.time_ns()
    receipt = out / 'result.json'
    receipt.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'state': report['state'], 'result': str(receipt)}))
    if report['state'] != 'v46-alpine-debug-basics-installed-and-verified':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
