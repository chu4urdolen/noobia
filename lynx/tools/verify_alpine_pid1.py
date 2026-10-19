"""Verify Lynx's native Alpine PID 1, OpenRC health and inherited SSH."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time

from lynx_wifi_v19_contact import BUILD, ssh_command

ROOT = Path(__file__).resolve().parent.parent
IMAGE = ROOT / 'linux-port/artifacts/persistent-openrc-v33-offline/nord3-persistent-openrc-v33-untested.img'
IMAGE_SHA = '1d65456979d8a48d31de77c987b8aaf9b5ac11af62c51d00fdaff68ad47e747f'


def receipt(path):
    path = path.resolve(strict=True)
    if not path.is_relative_to(ROOT / 'logs'):
        raise ValueError('Receipt outside Lynx logs')
    return json.loads(path.read_text()), str(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--contact', required=True, type=Path)
    parser.add_argument('--health', required=True, type=Path)
    parser.add_argument('--arm', required=True, type=Path)
    args = parser.parse_args()
    contact, contact_path = receipt(args.contact)
    health, health_path = receipt(args.health)
    arm, arm_path = receipt(args.arm)
    if hashlib.sha256(IMAGE.read_bytes()).hexdigest() != IMAGE_SHA:
        raise ValueError('V33 image differs')
    ip = contact.get('phone_ip', '')
    if (contact.get('state') != 'native-ssh-available' or
            contact.get('native_ssh_verified') is not True or
            contact.get('session_token') != BUILD['session_token'] or
            not re.fullmatch(r'192\.168\.100\.[1-9][0-9]?', ip) or
            health.get('state') != 'local-health-in-ram-verified' or
            health.get('contact_receipt') != contact_path or
            health.get('phone_ip') != ip or
            arm.get('state') != 'v33-openrc-armed' or
            arm.get('contact') != contact_path or
            arm.get('health') != health_path or
            arm.get('image_sha256') != IMAGE_SHA or
            not re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', arm.get('boot_id', ''))):
        raise ValueError('Pinned same-boot V33 evidence differs')
    os.umask(0o077)
    out = ROOT / 'logs' / ('v33-alpine-pid1-verification-' + str(time.time_ns()))
    out.mkdir(mode=0o700)
    report = {'state': 'starting', 'contact': contact_path, 'health': health_path,
              'arm': arm_path, 'image_sha256': IMAGE_SHA, 'phone_ip': ip,
              'phone_partition_writes': False, 'flash_performed': False,
              'created_ns': time.time_ns()}
    script = '''set -e
printf 'BOOT_ID='; cat /proc/sys/kernel/random/boot_id
printf 'PID1_EXE='; readlink /proc/1/exe
printf 'PID1_ROOT='; readlink /proc/1/root
printf 'ALPINE_RELEASE='; cat /proc/1/root/etc/alpine-release
printf 'ROOT_MOUNT='; grep -E '^/dev/sdc85 /run/lynx/persistent-alpine ext4 rw,' /proc/mounts
printf 'OPENRC_STATUS_BEGIN\\n'
/bin/busybox chroot /run/lynx/persistent-alpine /bin/rc-status -a
printf 'OPENRC_STATUS_END\\n'
/bin/busybox chroot /run/lynx/persistent-alpine /sbin/rc-service lynx-health status
printf 'HEALTH_SERVICE_STATUS=0\\n'
printf 'ALPINE_PYTHON='; /bin/busybox chroot /run/lynx/persistent-alpine /usr/bin/python3 --version
printf 'ALPINE_GIT='; /bin/busybox chroot /run/lynx/persistent-alpine /usr/bin/git --version
printf 'WIFI_ADDR='; ip -4 addr show dev wlan0 | grep 'inet 192.168.100.'
printf 'SSH_LISTENER='; netstat -lnt | grep ':22 '
/bin/busybox sh /run/lynx/lynx-health-supervisor.sh --once
'''
    try:
        result = subprocess.run(ssh_command(ip, script), capture_output=True, timeout=30)
        (out / 'stdout').write_bytes(result.stdout)
        (out / 'stderr').write_bytes(result.stderr)
        text = result.stdout.decode(errors='replace')
        expected = [
            'BOOT_ID=' + arm['boot_id'] + '\n',
            'PID1_EXE=/run/lynx/persistent-alpine/sbin/openrc-init\n',
            'PID1_ROOT=/run/lynx/persistent-alpine\n',
            'ALPINE_RELEASE=3.24.2\n',
            'ROOT_MOUNT=/dev/sdc85 /run/lynx/persistent-alpine ext4 rw,',
            'HEALTH_SERVICE_STATUS=0\n',
            'ALPINE_PYTHON=Python 3.',
            'ALPINE_GIT=git version ',
            'WIFI_ADDR=',
            'SSH_LISTENER=',
            'LYNX_HEALTH_OK ',
        ]
        if (result.returncode != 0 or any(value not in text for value in expected) or
                not re.search(r'(?m)^ lynx-health\s+\[\s*started\s*\]', text)):
            raise ValueError('Alpine PID 1, OpenRC, SSH or health verification refused')
        report.update(state='alpine-pid1-verified', boot_id=arm['boot_id'],
                      ssh_exit_code=result.returncode,
                      stdout_sha256=hashlib.sha256(result.stdout).hexdigest())
    except Exception as error:
        report.update(state='failed-or-incomplete', error=str(error))
    report['finished_ns'] = time.time_ns()
    (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'state': report['state'], 'result': str(out / 'result.json')}))
    if report['state'] != 'alpine-pid1-verified':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
