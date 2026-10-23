"""Read-only proof of Lynx's live logger and reserve rollback files."""

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
INIT_SHA = 'ebc6bb746aaf710d915c47036f92ce0c4ed23a185dfb5349b90e654bab7ba4ae'
FILES = {
    'logger': '/run/lynx/persistent-alpine/etc/init.d/lynx-local-logs',
    'logger_backup': '/run/lynx/persistent-alpine/root/lynx-rescue/lynx-local-logs-notice-v46.sh',
    'reserve': '/run/lynx/persistent-alpine/usr/libexec/lynx-battery-reserve.sh',
    'reserve_backup': '/run/lynx/persistent-alpine/root/lynx-rescue/battery-reserve-unplugged-v46.sh',
}


def receipt(path):
    path = path.resolve(strict=True)
    if not path.is_relative_to(ROOT / 'logs'):
        raise ValueError('Receipt outside Lynx logs')
    return path, json.loads(path.read_text())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verification', required=True, type=Path)
    parser.add_argument('--logger-update', required=True, type=Path)
    parser.add_argument('--reserve-rollback', required=True, type=Path)
    args = parser.parse_args()
    (boot_path, boot), (logger_path, logger), (reserve_path, reserve) = (
        receipt(x) for x in (args.verification, args.logger_update,
                             args.reserve_rollback))
    boot_id, ip = boot['boot_id'], boot['phone_ip']
    if (boot.get('state') != 'v46-autonomous-alpine-pid1-verified' or
            logger.get('state') != 'v46-local-logs-updated-and-running' or
            reserve.get('state') != 'v46-reserve-rollback-applied-for-next-boot' or
            logger.get('boot_id') != boot_id or reserve.get('boot_id') != boot_id or
            logger.get('phone_ip') != ip or reserve.get('phone_ip') != ip or
            not re.fullmatch(r'192\.168\.100\.[1-9][0-9]?', ip)):
        raise ValueError('Same-boot recovery receipts differ')
    expected = {'init': INIT_SHA, 'logger': logger['new_sha256'],
                'logger_backup': logger['old_sha256'],
                'reserve': reserve['old_sha256'],
                'reserve_backup': reserve['old_sha256']}
    command = (
        'set -eu; '
        f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{boot_id}"; '
        'test "$(awk \'$2=="/run/lynx/persistent-alpine" {print $3; exit}\' /proc/mounts)" = ext4; '
        'sha256sum /init; ' +
        ' '.join(f'sha256sum {path};' for path in FILES.values())
    )
    os.umask(0o077)
    out = ROOT / 'logs' / f'v46-live-recovery-audit-{time.time_ns()}'
    out.mkdir(mode=0o700)
    argv = ssh_command(ip, command)
    report = {'state': 'starting', 'boot_id': boot_id, 'phone_ip': ip,
              'verification': str(boot_path), 'logger_update': str(logger_path),
              'reserve_rollback': str(reserve_path), 'phone_writes': False,
              'expected_sha256': expected}
    try:
        run = subprocess.run(argv, capture_output=True, timeout=15)
        (out / 'stdout').write_bytes(run.stdout)
        (out / 'stderr').write_bytes(run.stderr)
        if run.returncode:
            raise ValueError('Pinned rescue SSH audit failed')
        found = {}
        for line in run.stdout.decode(errors='replace').splitlines():
            parts = line.split()
            if len(parts) != 2 or not re.fullmatch(r'[0-9a-f]{64}', parts[0]):
                raise ValueError('Unexpected checksum output')
            name = ('init' if parts[1] == '/init' else
                    next((key for key, path in FILES.items() if path == parts[1]), None))
            if name is None or name in found:
                raise ValueError('Unexpected or repeated checksum path')
            found[name] = parts[0]
        if found != expected:
            raise ValueError('Recovery file hashes differ')
        report.update(state='v46-live-recovery-files-verified',
                      stdout_sha256=hashlib.sha256(run.stdout).hexdigest())
    except Exception as error:
        report.update(state='failed-or-incomplete', error=str(error))
    report['finished_ns'] = time.time_ns()
    result = out / 'result.json'
    result.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'state': report['state'], 'result': str(result)}))
    if report['state'] != 'v46-live-recovery-files-verified':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
