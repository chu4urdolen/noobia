"""Request one guarded OpenRC reboot from a verified V46 Alpine boot."""
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
IMAGE = ROOT / 'linux-port/artifacts/persistent-alpine-v46-offline/nord3-persistent-alpine-v46-untested.img'
BUILD = IMAGE.parent / 'build-result.json'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verification', type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--prepare', action='store_true')
    mode.add_argument('--reboot', action='store_true')
    args = parser.parse_args()
    path = args.verification.resolve(strict=True)
    if not path.is_relative_to(ROOT / 'logs'):
        raise ValueError('Verification outside Lynx logs')
    verified = json.loads(path.read_text())
    build = json.loads(BUILD.read_text())
    boot_id, ip = verified['boot_id'], verified['phone_ip']
    if (verified['state'] != 'v46-autonomous-alpine-pid1-verified' or
            verified['image_sha256'] != build['image_sha256'] or
            hashlib.sha256(IMAGE.read_bytes()).hexdigest() != build['image_sha256'] or
            not re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', boot_id) or
            not re.fullmatch(r'192\.168\.100\.[1-9][0-9]?', ip)):
        raise ValueError('Exact V46 same-boot verification missing')
    preflight = ("set -eu; test \"$(cat /proc/sys/kernel/random/boot_id)\" = '" + boot_id +
                 "'; test \"$(cat /etc/alpine-release)\" = 3.24.2; "
                 "test \"$(readlink /proc/1/exe)\" = /sbin/openrc-init; "
                 "for x in /sys/class/power_supply/*/online; do "
                 "test -r \"$x\" || continue; test \"$(cat \"$x\")\" = 0; done; "
                 "/sbin/rc-service lynx-health status; "
                 "/sbin/openrc-shutdown --dry-run --reboot now")
    def ssh(command, timeout):
        argv = ssh_command(ip, command)
        argv[-2:-2] = ['-p', '2222']
        return subprocess.run(argv, capture_output=True, timeout=timeout)
    os.umask(0o077)
    out = ROOT / 'logs' / ('v46-openrc-reboot-' + str(time.time_ns()))
    out.mkdir(mode=0o700)
    receipt = out / 'result.json'
    report = {'state': 'starting', 'created_ns': time.time_ns(),
              'verification': str(path), 'old_boot_id': boot_id, 'phone_ip': ip,
              'image_sha256': build['image_sha256'],
              'direct_partition_operations': False,
              'normal_openrc_shutdown_may_sync_ext4': bool(args.reboot),
              'command': '/sbin/openrc-shutdown --reboot now' if args.reboot else None}
    try:
        check = ssh(preflight, 15)
        (out / 'preflight.stdout').write_bytes(check.stdout)
        (out / 'preflight.stderr').write_bytes(check.stderr)
        if check.returncode or b'Would send reboot to init' not in check.stdout:
            raise ValueError('Read-only reboot preflight refused')
        report['state'] = 'reboot-preflight-passed'
        receipt.write_text(json.dumps(report, indent=2) + '\n')
        if args.reboot:
            command = ("test \"$(cat /proc/sys/kernel/random/boot_id)\" = '" + boot_id +
                       "' && /sbin/openrc-shutdown --reboot now")
            try:
                sent = ssh(command, 12)
                (out / 'reboot.stdout').write_bytes(sent.stdout)
                (out / 'reboot.stderr').write_bytes(sent.stderr)
                report.update(state='reboot-command-sent', ssh_exit_code=sent.returncode)
            except subprocess.TimeoutExpired as error:
                (out / 'reboot.stdout').write_bytes(error.stdout or b'')
                (out / 'reboot.stderr').write_bytes(error.stderr or b'')
                report.update(state='reboot-command-sent', ssh_timed_out=True)
    except Exception as error:
        report.update(state='failed-or-incomplete', error=str(error))
    report['finished_ns'] = time.time_ns()
    receipt.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'state': report['state'], 'result': str(receipt)}))
    if report['state'] == 'failed-or-incomplete':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
