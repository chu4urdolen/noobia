"""Stage a charging-aware reserve guard on verified V46 Alpine; activate next boot."""

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
INIT_SHA = 'ebc6bb746aaf710d915c47036f92ce0c4ed23a185dfb5349b90e654bab7ba4ae'
OLD_INSTALL = ROOT / 'logs/v46-battery-reserve-install-1792699349648809360/result.json'
TARGET = '/usr/libexec/lynx-battery-reserve.sh'
BACKUP = '/root/lynx-rescue/battery-reserve-unplugged-v46.sh'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verification', required=True, type=Path)
    args = parser.parse_args()
    proof_path = args.verification.resolve(strict=True)
    if not proof_path.is_relative_to(ROOT / 'logs'):
        raise ValueError('Verification outside Lynx logs')
    proof = json.loads(proof_path.read_text())
    old = json.loads(OLD_INSTALL.read_text())
    boot_id, ip = proof['boot_id'], proof['phone_ip']
    if (proof.get('state') != 'v46-autonomous-alpine-pid1-verified' or
            old.get('state') != 'v46-battery-reserve-installed-and-running' or
            old.get('script_sha256') is None or
            not re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', boot_id) or
            not re.fullmatch(r'192\.168\.100\.[1-9][0-9]?', ip)):
        raise ValueError('Exact V46 and prior installed guard proof missing')
    script = SCRIPT.read_bytes()
    new_sha, old_sha = sha(script), old['script_sha256']
    if new_sha == old_sha:
        raise ValueError('Charging-aware guard source unchanged')
    subprocess.run(['/bin/sh', '-n', str(SCRIPT)], check=True)
    subprocess.run(['python3', str(ROOT / 'tools/test_lynx_battery_reserve.py')],
                   check=True, capture_output=True)

    os.umask(0o077)
    out = ROOT / 'logs' / f'v46-charging-reserve-update-{time.time_ns()}'
    out.mkdir(mode=0o700)
    result = out / 'result.json'
    report = {'state': 'starting', 'boot_id': boot_id, 'phone_ip': ip,
              'verification': str(proof_path), 'old_install': str(OLD_INSTALL),
              'old_sha256': old_sha, 'new_sha256': new_sha,
              'boot_partition_writes': False, 'charging_hardware_writes': False,
              'activation': 'next boot; running old guard remains active',
              'steps': []}

    def step(name, command, payload=None, timeout=20):
        argv = ssh_command(ip, command)
        argv[-2:-2] = ['-p', '2222']
        run = subprocess.run(argv, input=payload, capture_output=True, timeout=timeout)
        (out / f'{name}.stdout').write_bytes(run.stdout)
        (out / f'{name}.stderr').write_bytes(run.stderr)
        report['steps'].append({'name': name, 'exit_code': run.returncode,
                                'stdout_sha256': sha(run.stdout),
                                'stderr_sha256': sha(run.stderr)})
        if run.returncode:
            raise ValueError(f'{name} failed; inspect private receipt')
        return run.stdout.decode(errors='replace')

    common = (
        'set -eu; '
        f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{boot_id}"; '
        'test "$(readlink /proc/1/exe)" = /sbin/openrc-init; '
        'test "$(cat /etc/alpine-release)" = 3.24.2; '
        'test "$(awk \'$2=="/" {print $3; exit}\' /proc/mounts)" = ext4; '
        '/sbin/rc-service lynx-health status >/dev/null; '
        '/sbin/rc-service lynx-battery-reserve status >/dev/null; '
        '/sbin/rc-service lynx-maintenance status >/dev/null; '
    )
    try:
        rescue = subprocess.run(
            ssh_command(ip,
                'set -eu; '
                f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{boot_id}"; '
                f'test "$(sha256sum /init | cut -c1-64)" = "{INIT_SHA}"; '
                'printf LYNX_RESCUE_SSH_READY'),
            capture_output=True, timeout=12)
        (out / 'rescue_preflight.stdout').write_bytes(rescue.stdout)
        (out / 'rescue_preflight.stderr').write_bytes(rescue.stderr)
        if rescue.returncode or b'LYNX_RESCUE_SSH_READY' not in rescue.stdout:
            raise ValueError('Pinned rescue SSH is unavailable')
        report['rescue_ssh_verified'] = True
        preflight = (
            common + f'test "$(sha256sum {TARGET} | cut -c1-64)" = "{old_sha}"; '
            f'test ! -e {BACKUP}; '
            'count=0; while [ "$count" -lt 3 ]; do '
            'sample=$(cat /sys/bus/i2c/devices/7-0055/battery_snapshot); '
            'printf "%s\\n" "$sample" | grep -qx gauge_device_type=42495; '
            'printf "%s\\n" "$sample" | grep -qx capacity_error=0; '
            'printf "%s\\n" "$sample" | grep -qx current_error=0; '
            'printf "%s\\n" "$sample" | grep -qx temperature_error=0; '
            'capacity=$(printf "%s\\n" "$sample" | sed -n "s/^capacity_percent=//p"); '
            'current=$(printf "%s\\n" "$sample" | sed -n "s/^gauge_current_ma_signed=//p"); '
            'temperature=$(printf "%s\\n" "$sample" | sed -n "s/^temperature_millidegrees_celsius=//p"); '
            'case "$capacity:$current:$temperature" in *[!0-9:]*|::*|*::*) exit 1;; esac; '
            'test "$capacity" -ge 11; test "$capacity" -le 30; '
            'test "$current" -ge 75; test "$temperature" -ge 10000; '
            'test "$temperature" -lt 35000; '
            'printf "SAMPLE capacity=%s current=%s temperature=%s\\n" '
            '"$capacity" "$current" "$temperature"; '
            'count=$((count+1)); [ "$count" -eq 3 ] || sleep 5; done; '
            'printf LYNX_CHARGING_RESERVE_UPDATE_READY'
        )
        output = step('preflight', preflight, timeout=30)
        if output.count('SAMPLE capacity=') != 3 or 'LYNX_CHARGING_RESERVE_UPDATE_READY' not in output:
            raise ValueError('Three positive-current preflight samples missing')
        step('stage', 'cat > /run/lynx/battery-reserve-charging.stage', payload=script)
        install = (
            common +
            f'test "$(sha256sum /run/lynx/battery-reserve-charging.stage | cut -c1-64)" = "{new_sha}"; '
            f'test "$(sha256sum {TARGET} | cut -c1-64)" = "{old_sha}"; '
            'install -d -m 0700 /root/lynx-rescue; '
            f'cp -p {TARGET} {BACKUP}; '
            f'test "$(sha256sum {BACKUP} | cut -c1-64)" = "{old_sha}"; '
            f'install -m 0755 /run/lynx/battery-reserve-charging.stage {TARGET}.new; '
            f'mv {TARGET}.new {TARGET}; '
            f'test "$(sha256sum {TARGET} | cut -c1-64)" = "{new_sha}"; '
            f'/bin/sh {TARGET} --once; '
            '/sbin/rc-service lynx-battery-reserve status >/dev/null; '
            'printf LYNX_CHARGING_RESERVE_STAGED'
        )
        if 'LYNX_CHARGING_RESERVE_STAGED' not in step('install', install, timeout=25):
            raise ValueError('Staged update marker missing')
        report['state'] = 'v46-charging-reserve-staged-for-next-boot'
    except Exception as error:
        report.update(state='failed-or-incomplete', error=str(error))
        try:
            probe = subprocess.run(
                ssh_command(ip, f'test -f {BACKUP}'), capture_output=True,
                timeout=12)
            if probe.returncode:
                report['old_guard_restored'] = 'not-needed-no-backup-created'
                raise FileNotFoundError('No backup to restore')
            fallback = (
                'set -eu; '
                f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{boot_id}"; '
                f'test "$(sha256sum {BACKUP} | cut -c1-64)" = "{old_sha}"; '
                f'cp -p {BACKUP} {TARGET}.restore; '
                f'mv {TARGET}.restore {TARGET}; '
                f'test "$(sha256sum {TARGET} | cut -c1-64)" = "{old_sha}"; '
                'printf LYNX_OLD_RESERVE_RESTORED'
            )
            report['old_guard_restored'] = ('LYNX_OLD_RESERVE_RESTORED' in
                                            step('restore', fallback))
        except Exception as fallback_error:
            if report.get('old_guard_restored') != 'not-needed-no-backup-created':
                report['fallback_error'] = str(fallback_error)
    report['finished_ns'] = time.time_ns()
    result.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'state': report['state'], 'result': str(result),
                      'old_guard_restored': report.get('old_guard_restored')}))
    if report['state'] != 'v46-charging-reserve-staged-for-next-boot':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
