"""Verify Alpine-owned SSH on port 2222 during a proven V46 boot."""
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verification', required=True, type=Path)
    args = parser.parse_args()
    path = args.verification.resolve(strict=True)
    if not path.is_relative_to(ROOT / 'logs'):
        raise ValueError('Verification outside Lynx logs')
    verified = json.loads(path.read_text())
    boot_id, ip = verified['boot_id'], verified['phone_ip']
    if (verified['state'] != 'v46-autonomous-alpine-pid1-verified' or
            not re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', boot_id) or
            not re.fullmatch(r'192\.168\.100\.[1-9][0-9]?', ip)):
        raise ValueError('V46 same-boot verification missing')
    command = ("set -eu; test \"$(cat /proc/sys/kernel/random/boot_id)\" = '" + boot_id +
               "'; test \"$(cat /etc/alpine-release)\" = 3.24.2; "
               "test \"$(readlink /proc/1/exe)\" = /sbin/openrc-init; "
               "id; /sbin/rc-service lynx-dropbear status; "
               "echo LYNX_V46_ALPINE_NATIVE_SSH_2222_VERIFIED")
    argv = ssh_command(ip, command)
    argv[-2:-2] = ['-p', '2222']
    os.umask(0o077)
    out = ROOT / 'logs' / ('v46-alpine-native-ssh-' + str(time.time_ns()))
    out.mkdir(mode=0o700)
    result = {'state': 'starting', 'created_ns': time.time_ns(),
              'verification': str(path), 'boot_id': boot_id, 'phone_ip': ip,
              'port': 2222, 'phone_partition_writes': False}
    try:
        probe = subprocess.run(argv, capture_output=True, timeout=15)
        (out / 'stdout').write_bytes(probe.stdout)
        (out / 'stderr').write_bytes(probe.stderr)
        data = probe.stdout.decode(errors='replace')
        if (probe.returncode or 'uid=0(root)' not in data or
                'LYNX_V46_ALPINE_NATIVE_SSH_2222_VERIFIED' not in data):
            raise ValueError('Alpine-owned pinned SSH identity or service refused')
        result.update(state='v46-alpine-native-ssh-verified',
                      stdout_sha256=hashlib.sha256(probe.stdout).hexdigest())
    except Exception as error:
        result.update(state='failed-or-incomplete', error=str(error))
    result['finished_ns'] = time.time_ns()
    receipt = out / 'result.json'
    receipt.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'state': result['state'], 'result': str(receipt)}))
    if result['state'] != 'v46-alpine-native-ssh-verified':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
