"""Install the tested battery-reserve OpenRC service over pinned Alpine SSH."""

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


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verification', required=True, type=Path)
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
    for path in (SCRIPT, SERVICE):
        subprocess.run(['/bin/sh', '-n', str(path)], check=True)
    subprocess.run(['python3', str(ROOT / 'tools/test_lynx_battery_reserve.py')],
                   check=True, capture_output=True)
    os.umask(0o077)
    out = ROOT / 'logs' / f'v46-battery-reserve-install-{time.time_ns()}'
    out.mkdir(mode=0o700)
    receipt = {'state': 'starting', 'boot_id': boot_id, 'phone_ip': ip,
               'verification': str(proof_path), 'script_sha256': sha(SCRIPT),
               'service_sha256': sha(SERVICE), 'boot_partition_writes': False,
               'charging_changes': False, 'steps': []}

    def remote(name, command, timeout=20, data=None):
        argv = ssh_command(ip, command)
        argv[-2:-2] = ['-p', '2222']
        run = subprocess.run(argv, input=data, capture_output=True, timeout=timeout)
        (out / f'{name}.stdout').write_bytes(run.stdout)
        (out / f'{name}.stderr').write_bytes(run.stderr)
        receipt['steps'].append({'name': name, 'exit_code': run.returncode,
                                 'stdout_sha256': hashlib.sha256(run.stdout).hexdigest(),
                                 'stderr_sha256': hashlib.sha256(run.stderr).hexdigest()})
        if run.returncode:
            raise ValueError(f'{name} failed; see private receipt')
        return run.stdout.decode(errors='replace')

    preflight = (
        'set -eu; '
        f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{boot_id}"; '
        'test "$(cat /etc/alpine-release)" = 3.24.2; '
        'test "$(readlink /proc/1/exe)" = /sbin/openrc-init; '
        'test "$(awk \'$2=="/" {print $3; exit}\' /proc/mounts)" = ext4; '
        '/sbin/openrc-shutdown --dry-run --poweroff now >/dev/null; '
        '/sbin/rc-service lynx-health status >/dev/null; '
        '/bin/sh /run/lynx/lynx-health-supervisor.sh --once >/dev/null; '
        'test ! -e /etc/init.d/lynx-battery-reserve; '
        'test ! -e /usr/libexec/lynx-battery-reserve.sh; '
        'sample=$(cat /sys/bus/i2c/devices/7-0055/battery_snapshot); '
        'capacity=$(printf "%s\\n" "$sample" | sed -n "s/^capacity_percent=//p"); '
        'temperature=$(printf "%s\\n" "$sample" | sed -n "s/^temperature_millidegrees_celsius=//p"); '
        'printf "%s\\n" "$sample" | grep -qx capacity_error=0; '
        'printf "%s\\n" "$sample" | grep -qx temperature_error=0; '
        'printf "%s\\n" "$sample" | grep -qx gauge_device_type=42495; '
        'case "$capacity:$temperature" in *[!0-9:]*|:*) exit 1;; esac; '
        'test "$capacity" -ge 40; test "$capacity" -le 100; '
        'test "$temperature" -gt 0; test "$temperature" -lt 40000; '
        'count=0; for d in /sys/class/power_supply/*; do '
        '[ -r "$d/online" ] || continue; '
        'test "$(cat "$d/online")" = 0; count=$((count+1)); done; '
        'test "$count" -ge 1; '
        'printf "LYNX_RESERVE_PREFLIGHT_OK capacity=%s temperature=%s\\n" "$capacity" "$temperature"'
    )
    try:
        output = remote('preflight', preflight)
        if 'LYNX_RESERVE_PREFLIGHT_OK' not in output:
            raise ValueError('Preflight marker missing')
        for name, source, target in (
                ('stage_script', SCRIPT, '/run/lynx/battery-reserve.stage'),
                ('stage_service', SERVICE, '/run/lynx/battery-reserve-openrc.stage')):
            remote(name, f'cat > {target}', data=source.read_bytes())
        install = (
            'set -eu; '
            f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{boot_id}"; '
            f'test "$(sha256sum /run/lynx/battery-reserve.stage | cut -c1-64)" = "{sha(SCRIPT)}"; '
            f'test "$(sha256sum /run/lynx/battery-reserve-openrc.stage | cut -c1-64)" = "{sha(SERVICE)}"; '
            'install -m 0755 /run/lynx/battery-reserve.stage /usr/libexec/lynx-battery-reserve.sh.new; '
            'install -m 0755 /run/lynx/battery-reserve-openrc.stage /etc/init.d/lynx-battery-reserve.new; '
            'mv /usr/libexec/lynx-battery-reserve.sh.new /usr/libexec/lynx-battery-reserve.sh; '
            'mv /etc/init.d/lynx-battery-reserve.new /etc/init.d/lynx-battery-reserve; '
            '/bin/sh /usr/libexec/lynx-battery-reserve.sh --once; '
            '/sbin/rc-update add lynx-battery-reserve default; '
            '/sbin/rc-service lynx-battery-reserve start; '
            '/sbin/rc-service lynx-battery-reserve status; '
            'test -L /etc/runlevels/default/lynx-battery-reserve; '
            'test -r /run/lynx/battery-reserve/pid; '
            'kill -0 "$(cat /run/lynx/battery-reserve/pid)"; '
            'printf LYNX_RESERVE_INSTALLED_AND_RUNNING'
        )
        output = remote('install', install, timeout=35)
        if 'LYNX_RESERVE_INSTALLED_AND_RUNNING' not in output:
            raise ValueError('Installed service proof missing')
        receipt['state'] = 'v46-battery-reserve-installed-and-running'
    except Exception as error:
        receipt.update(state='failed-or-incomplete', error=str(error))
    receipt['finished_ns'] = time.time_ns()
    result = out / 'result.json'
    result.write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps({'state': receipt['state'], 'result': str(result)}))
    if receipt['state'] != 'v46-battery-reserve-installed-and-running':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
