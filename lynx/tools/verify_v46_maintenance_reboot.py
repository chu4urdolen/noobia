"""Verify maintenance autostart and retained logs across a V46 OpenRC reboot."""

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
BOOT_RE = re.compile(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}')


def read_receipt(path):
    path = path.resolve(strict=True)
    if not path.is_relative_to(ROOT / 'logs'):
        raise ValueError('Receipt outside Lynx logs')
    return path, json.loads(path.read_text())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--old-verification', required=True, type=Path)
    parser.add_argument('--new-verification', required=True, type=Path)
    parser.add_argument('--old-log-proof', required=True, type=Path)
    args = parser.parse_args()
    old_path, old = read_receipt(args.old_verification)
    new_path, new = read_receipt(args.new_verification)
    log_path, log = read_receipt(args.old_log_proof)
    old_id, new_id = old['boot_id'], new['boot_id']
    if (old.get('state') != 'v46-autonomous-alpine-pid1-verified' or
            new.get('state') != 'v46-autonomous-alpine-pid1-verified' or
            log.get('state') != 'v46-local-logs-verified' or
            log.get('boot_id') != old_id or old_id == new_id or
            old.get('image_sha256') != new.get('image_sha256') or
            not BOOT_RE.fullmatch(old_id) or not BOOT_RE.fullmatch(new_id) or
            not re.fullmatch(r'192\.168\.100\.[1-9][0-9]?', new['phone_ip']) or
            not re.fullmatch(r'LYNX_LOG_PROOF_[0-9]+', log['marker'])):
        raise ValueError('Cross-boot receipts do not match a V46 reboot')
    marker = log['marker']
    command = (
        'set -eu; '
        f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{new_id}"; '
        'test "$(readlink /proc/1/exe)" = /sbin/openrc-init; '
        'test "$(cat /etc/alpine-release)" = 3.24.2; '
        'for service in lynx-health lynx-battery-reserve lynx-local-logs '
        'lynx-wifi lynx-dropbear lynx-maintenance; do '
        '/sbin/rc-service "$service" status >/dev/null; done; '
        '/bin/sh /usr/libexec/lynx-maintenance-watch.sh --once; '
        'guard_pid=$(cat /run/lynx/v40-charger-guard.pid); '
        'case "$guard_pid" in ""|*[!0-9]*) exit 1;; esac; '
        'kill -0 "$guard_pid"; '
        f'grep -Fq "{marker}_KERNEL" /var/log/lynx/messages*; '
        f'grep -Fq "{marker}" /var/log/lynx/messages*; '
        'test -r /var/log/lynx/messages; '
        'count=0; for d in /sys/class/power_supply/*; do '
        '[ -r "$d/online" ] || continue; test "$(cat "$d/online")" = 0; count=$((count+1)); done; '
        'test "$count" -ge 1; '
        'printf LYNX_V46_MAINTENANCE_REBOOT_VERIFIED'
    )
    argv = ssh_command(new['phone_ip'], command)
    argv[-2:-2] = ['-p', '2222']
    os.umask(0o077)
    out = ROOT / 'logs' / f'v46-maintenance-reboot-{time.time_ns()}'
    out.mkdir(mode=0o700)
    report = {'state': 'starting', 'old_boot_id': old_id, 'new_boot_id': new_id,
              'old_verification': str(old_path), 'new_verification': str(new_path),
              'old_log_proof': str(log_path), 'marker': marker,
              'phone_partition_writes': False, 'read_only': True}
    try:
        run = subprocess.run(argv, capture_output=True, timeout=20)
        (out / 'stdout').write_bytes(run.stdout)
        (out / 'stderr').write_bytes(run.stderr)
        if (run.returncode or b'LYNX_MAINTENANCE_OK ' not in run.stdout or
                b'LYNX_V46_MAINTENANCE_REBOOT_VERIFIED' not in run.stdout):
            raise ValueError('New boot services or retained log marker missing')
        report.update(state='v46-maintenance-reboot-verified',
                      stdout_sha256=hashlib.sha256(run.stdout).hexdigest())
    except Exception as error:
        report.update(state='failed-or-incomplete', error=str(error))
    report['finished_ns'] = time.time_ns()
    result = out / 'result.json'
    result.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'state': report['state'], 'result': str(result),
                      'old_boot_id': old_id, 'new_boot_id': new_id}))
    if report['state'] != 'v46-maintenance-reboot-verified':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
