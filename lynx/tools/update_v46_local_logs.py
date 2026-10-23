"""Replace Lynx's proven logger under same-boot health and battery guards."""

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
    predecessor = parser.add_mutually_exclusive_group(required=True)
    predecessor.add_argument('--old-install', type=Path)
    predecessor.add_argument('--old-update', type=Path)
    args = parser.parse_args()
    paths = [x.resolve(strict=True) for x in
             (args.verification, args.old_install or args.old_update)]
    if any(not x.is_relative_to(ROOT / 'logs') for x in paths):
        raise ValueError('Receipt outside Lynx logs')
    boot, old = [json.loads(x.read_text()) for x in paths]
    boot_id, ip = boot['boot_id'], boot['phone_ip']
    expected_old_state = ('v46-local-logs-installed-and-running' if args.old_install
                          else 'v46-local-logs-updated-and-running')
    if (boot.get('state') != 'v46-autonomous-alpine-pid1-verified' or
            old.get('state') != expected_old_state or
            old.get('boot_id') == boot_id or
            not re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', boot_id) or
            not re.fullmatch(r'192\.168\.100\.[1-9][0-9]?', ip)):
        raise ValueError('V46 new boot and old logger receipt missing')
    subprocess.run(['/bin/sh', '-n', str(SOURCE)], check=True)
    data = SOURCE.read_bytes()
    new_sha = hashlib.sha256(data).hexdigest()
    old_sha = old['service_sha256'] if args.old_install else old['new_sha256']
    if new_sha == old_sha:
        raise ValueError('Logger source unchanged')
    os.umask(0o077)
    out = ROOT / 'logs' / f'v46-local-logs-update-{time.time_ns()}'
    out.mkdir(mode=0o700)
    report = {'state': 'starting', 'boot_id': boot_id, 'phone_ip': ip,
              'verification': str(paths[0]), 'predecessor': str(paths[1]),
              'old_sha256': old_sha, 'new_sha256': new_sha,
              'boot_partition_writes': False, 'steps': []}

    def step(name, command, payload=None, timeout=25):
        argv = ssh_command(ip, command)
        argv[-2:-2] = ['-p', '2222']
        run = subprocess.run(argv, input=payload, capture_output=True, timeout=timeout)
        (out / f'{name}.stdout').write_bytes(run.stdout)
        (out / f'{name}.stderr').write_bytes(run.stderr)
        report['steps'].append({'name': name, 'exit_code': run.returncode,
                                'stdout_sha256': hashlib.sha256(run.stdout).hexdigest()})
        if run.returncode:
            raise ValueError(f'{name} failed; see private streams')
        return run.stdout.decode(errors='replace')

    backup = '/run/lynx/lynx-local-logs.service.old'
    target = '/etc/init.d/lynx-local-logs'
    try:
        preflight = (
            'set -eu; '
            f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{boot_id}"; '
            'test "$(readlink /proc/1/exe)" = /sbin/openrc-init; '
            f'test "$(sha256sum {target} | cut -c1-64)" = "{old_sha}"; '
            '/sbin/rc-service lynx-health status >/dev/null; '
            '/sbin/rc-service lynx-battery-reserve status >/dev/null; '
            '/sbin/rc-service lynx-maintenance status >/dev/null; '
            '/sbin/rc-service lynx-local-logs status >/dev/null; '
            'sample=$(cat /sys/bus/i2c/devices/7-0055/battery_snapshot); '
            'capacity=$(printf "%s\\n" "$sample" | sed -n "s/^capacity_percent=//p"); '
            'printf "%s\\n" "$sample" | grep -qx capacity_error=0; '
            'case "$capacity" in ""|*[!0-9]*) exit 1;; esac; '
            'test "$capacity" -ge 40; test "$capacity" -le 100; '
            'count=0; for d in /sys/class/power_supply/*; do '
            '[ -r "$d/online" ] || continue; '
            'test "$(cat "$d/online")" = 0; count=$((count+1)); done; '
            'test "$count" -ge 1; '
            f'test ! -e {backup}; '
            'printf LYNX_LOG_UPDATE_READY'
        )
        if 'LYNX_LOG_UPDATE_READY' not in step('preflight', preflight):
            raise ValueError('Update preflight marker missing')
        step('stage_new', 'cat > /run/lynx/lynx-local-logs.service.new', payload=data)
        install = (
            'set -eu; '
            f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{boot_id}"; '
            f'test "$(sha256sum /run/lynx/lynx-local-logs.service.new | cut -c1-64)" = "{new_sha}"; '
            f'cp -p {target} {backup}; '
            f'test "$(sha256sum {backup} | cut -c1-64)" = "{old_sha}"; '
            f'install -m 0755 /run/lynx/lynx-local-logs.service.new {target}.new; '
            f'mv {target}.new {target}; '
            '/sbin/rc-service lynx-local-logs restart; '
            '/sbin/rc-service lynx-local-logs status; '
            f'test "$(sha256sum {target} | cut -c1-64)" = "{new_sha}"; '
            'printf LYNX_LOGGER_UPDATED'
        )
        if 'LYNX_LOGGER_UPDATED' not in step('update', install, timeout=35):
            raise ValueError('Logger update marker missing')
        report['state'] = 'v46-local-logs-updated-and-running'
    except Exception as error:
        report.update(state='failed-or-incomplete', error=str(error))
        try:
            fallback = (
                'set -eu; '
                f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{boot_id}"; '
                f'test "$(sha256sum {backup} | cut -c1-64)" = "{old_sha}"; '
                f'cp -p {backup} {target}.restore; '
                f'mv {target}.restore {target}; '
                '/sbin/rc-service lynx-local-logs restart; '
                '/sbin/rc-service lynx-local-logs status; '
                'printf LYNX_OLD_LOGGER_RESTORED'
            )
            report['old_service_restored'] = 'LYNX_OLD_LOGGER_RESTORED' in step(
                'restore_old', fallback, timeout=35)
        except Exception as fallback_error:
            report['fallback_error'] = str(fallback_error)
    report['finished_ns'] = time.time_ns()
    result = out / 'result.json'
    result.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'state': report['state'], 'result': str(result),
                      'old_service_restored': report.get('old_service_restored')}))
    if report['state'] != 'v46-local-logs-updated-and-running':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
