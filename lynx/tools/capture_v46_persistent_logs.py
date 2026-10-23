"""Save Lynx's private persistent diagnostics over pinned Alpine SSH."""

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import tarfile
import time

from lynx_wifi_v19_contact import ssh_command


ROOT = Path(__file__).resolve().parent.parent
BOOT_ID = re.compile(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}')
IP = re.compile(r'192\.168\.100\.[1-9][0-9]?')
MAX_ARCHIVE = 16 * 1024 * 1024


def remote(ip, command, timeout=30):
    argv = ssh_command(ip, command)
    argv[-2:-2] = ['-p', '2222']
    return subprocess.run(argv, capture_output=True, timeout=timeout)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verification', required=True, type=Path)
    args = parser.parse_args()
    verified = args.verification.resolve(strict=True)
    if not verified.is_relative_to(ROOT / 'logs'):
        raise ValueError('Verification outside Lynx logs')
    proof = json.loads(verified.read_text())
    boot_id, ip = proof['boot_id'], proof['phone_ip']
    if (proof.get('state') != 'v46-autonomous-alpine-pid1-verified' or
            not BOOT_ID.fullmatch(boot_id) or not IP.fullmatch(ip)):
        raise ValueError('No exact same-boot Lynx proof')

    os.umask(0o077)
    out = ROOT / 'logs' / f'v46-persistent-logs-{time.time_ns()}'
    out.mkdir(mode=0o700)
    report = {'state': 'starting', 'verification': str(verified),
              'boot_id': boot_id, 'phone_ip': ip, 'phone_writes': False}
    try:
        preflight = (
            'set -eu; '
            f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{boot_id}"; '
            'test "$(readlink /proc/1/exe)" = /sbin/openrc-init; '
            'test "$(cat /etc/alpine-release)" = 3.24.2; '
            'test "$(awk \'$2=="/" {print $3; exit}\' /proc/mounts)" = ext4; '
            'test "$(stat -c %a /var/log/lynx)" = 700; '
            'du -sk /var/log/lynx'
        )
        check = remote(ip, preflight)
        (out / 'preflight.stdout').write_bytes(check.stdout)
        (out / 'preflight.stderr').write_bytes(check.stderr)
        if check.returncode:
            raise ValueError('Identity, mount, or log privacy preflight failed')
        size_kib = int(check.stdout.split()[0])
        if size_kib * 1024 > MAX_ARCHIVE:
            raise ValueError('Persistent logs exceed archive size bound')
        archive = remote(ip, f'{preflight}; /bin/busybox tar -C /var/log -cf - lynx')
        (out / 'transfer.stderr').write_bytes(archive.stderr)
        if archive.returncode or len(archive.stdout) > MAX_ARCHIVE:
            raise ValueError('Bounded log transfer failed')
        # The second preflight prints du output; strip its first line before tar.
        first_line, marker, data = archive.stdout.partition(b'\n')
        if not marker or first_line != check.stdout.rstrip(b'\n'):
            raise ValueError('Repeated preflight differs')
        with tarfile.open(fileobj=io.BytesIO(data), mode='r:') as bundle:
            members = bundle.getmembers()
            if not members or any(not item.name.startswith('lynx/') and
                                  item.name != 'lynx' or item.issym() or item.islnk()
                                  for item in members):
                raise ValueError('Unexpected archive member')
        (out / 'lynx-logs.tar').write_bytes(data)
        report.update(state='v46-persistent-logs-captured',
                      archive_bytes=len(data),
                      archive_sha256=hashlib.sha256(data).hexdigest(),
                      members=[item.name for item in members])
    except Exception as error:
        report.update(state='failed-or-incomplete', error=str(error))
    report['finished_ns'] = time.time_ns()
    result = out / 'result.json'
    result.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'state': report['state'], 'result': str(result)}))
    if report['state'] != 'v46-persistent-logs-captured':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
