"""Install signed Alpine Dropbear packages on the verified V33 persistent root.

This changes only the mounted Alpine userdata filesystem. It neither starts
nor enables the new service, so the existing BusyBox SSH listener stays put.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from lynx_wifi_v19_contact import ssh_command

ROOT = Path(__file__).resolve().parent.parent
IMAGE = ROOT / 'linux-port/artifacts/persistent-openrc-v33-offline/nord3-persistent-openrc-v33-untested.img'
IMAGE_SHA = '1d65456979d8a48d31de77c987b8aaf9b5ac11af62c51d00fdaff68ad47e747f'
PACKAGES = ('dropbear=2026.91-r0', 'dropbear-openrc=2026.91-r0')
IP = '192.168.100.4'


def remote(command, timeout=20):
    return subprocess.run(ssh_command(IP, command), capture_output=True, timeout=timeout)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--arm-receipt', required=True, type=Path)
    parser.add_argument('--install', action='store_true')
    args = parser.parse_args()
    receipt_path = args.arm_receipt.resolve(strict=True)
    if not receipt_path.is_relative_to(ROOT / 'logs'):
        raise ValueError('Arm receipt outside Lynx logs')
    arm = json.loads(receipt_path.read_text())
    if (arm.get('state') != 'v33-openrc-armed' or
            arm.get('image_sha256') != IMAGE_SHA or
            hashlib.sha256(IMAGE.read_bytes()).hexdigest() != IMAGE_SHA):
        raise ValueError('V33 image or arm receipt differs')
    if not args.install:
        print(json.dumps({'state': 'offline-install-held', 'packages': PACKAGES,
                          'phone_contacted': False, 'partition_writes': False}))
        return
    os.umask(0o077)
    out = ROOT / 'logs' / ('alpine-dropbear-install-' + str(time.time_ns()))
    out.mkdir(mode=0o700)
    report = {'state': 'starting', 'arm_receipt': str(receipt_path),
              'boot_id': arm['boot_id'], 'packages': PACKAGES,
              'partition_scope': ['userdata Alpine ext4'], 'boot_image_changed': False,
              'service_started': False, 'service_enabled': False,
              'created_ns': time.time_ns(), 'steps': []}
    def save():
        (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    def step(name, command, timeout=20):
        report['state'] = name + '-issued'; save()
        result = remote(command, timeout=timeout)
        (out / (name + '.stdout')).write_bytes(result.stdout)
        (out / (name + '.stderr')).write_bytes(result.stderr)
        report['steps'].append({'name': name, 'exit_code': result.returncode,
                                'stdout_sha256': hashlib.sha256(result.stdout).hexdigest(),
                                'stderr_sha256': hashlib.sha256(result.stderr).hexdigest()})
        save()
        if result.returncode:
            raise ValueError(name + ' failed; inspect captured output')
        return result.stdout.decode(errors='replace')
    save()
    try:
        pre = step('preflight', '''set -eu
test "$(cat /proc/sys/kernel/random/boot_id)" = "''' + arm['boot_id'] + '''"
test "$(readlink /proc/1/exe)" = /run/lynx/persistent-alpine/sbin/openrc-init
test "$(cat /proc/1/root/etc/alpine-release)" = 3.24.2
grep -Eq '^/dev/sdc85 /run/lynx/persistent-alpine ext4 rw,' /proc/mounts
test ! -x /run/lynx/persistent-alpine/usr/sbin/dropbear
/bin/busybox sh /run/lynx/lynx-health-supervisor.sh --once
date -u +%s
''')
        if 'LYNX_HEALTH_OK ' not in pre:
            raise ValueError('Phone health preflight missing')
        if abs(int(pre.splitlines()[-1]) - int(time.time())) > 10:
            raise ValueError('Phone clock differs from Nexus by more than 10 seconds')
        simulation = step('simulate', '/bin/busybox chroot /run/lynx/persistent-alpine /sbin/apk add --simulate ' + ' '.join(PACKAGES), timeout=30)
        if 'dropbear' not in simulation or 'OK:' not in simulation:
            raise ValueError('Signed package simulation differs')
        step('install', '/bin/busybox chroot /run/lynx/persistent-alpine /sbin/apk add ' + ' '.join(PACKAGES), timeout=120)
        post = step('postcheck', '''set -eu
test "$(cat /proc/sys/kernel/random/boot_id)" = "''' + arm['boot_id'] + '''"
test "$(readlink /proc/1/exe)" = /run/lynx/persistent-alpine/sbin/openrc-init
test -x /run/lynx/persistent-alpine/usr/sbin/dropbear
test -x /run/lynx/persistent-alpine/etc/init.d/dropbear
/bin/busybox chroot /run/lynx/persistent-alpine /sbin/apk info -e dropbear dropbear-openrc
! netstat -lnt | grep -q ':2222 '
/bin/busybox sh /run/lynx/lynx-health-supervisor.sh --once
''')
        if 'LYNX_HEALTH_OK ' not in post:
            raise ValueError('Phone health postcheck missing')
        report['state'] = 'signed-dropbear-installed-service-held'
    except Exception as error:
        report.update(state='failed-or-incomplete', error=str(error))
    report['finished_ns'] = time.time_ns()
    save()
    print(json.dumps({'state': report['state'], 'result': str(out / 'result.json')}))
    if report['state'] != 'signed-dropbear-installed-service-held':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
