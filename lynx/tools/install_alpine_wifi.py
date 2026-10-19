"""Install signed Alpine Wi-Fi tools on Lynx's mounted persistent root.

The current BusyBox Wi-Fi processes and rescue SSH remain running. This does
not activate or enable any networking service.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time

from lynx_wifi_v19_contact import ssh_command

ROOT = Path(__file__).resolve().parent.parent
IP = '192.168.100.4'
PACKAGES = ('wpa_supplicant=2.11-r4', 'wpa_supplicant-openrc=2.11-r4',
            'iproute2=7.0.0-r0')


def remote(command, timeout=25):
    return subprocess.run(ssh_command(IP, command), capture_output=True,
                          timeout=timeout)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--arm-receipt', required=True, type=Path)
    parser.add_argument('--install', action='store_true')
    args = parser.parse_args()
    arm_path = args.arm_receipt.resolve(strict=True)
    if not arm_path.is_relative_to(ROOT / 'logs'):
        raise ValueError('Arm receipt outside Lynx logs')
    arm = json.loads(arm_path.read_text())
    if arm.get('state') != 'v33-openrc-armed':
        raise ValueError('Expected verified V33 arm receipt')
    if not args.install:
        print(json.dumps({'state': 'held', 'packages': PACKAGES,
                          'phone_contacted': False, 'partition_writes': False}))
        return
    os.umask(0o077)
    out = ROOT / 'logs' / ('alpine-wifi-install-' + str(time.time_ns()))
    out.mkdir(mode=0o700)
    report = {'state': 'starting', 'arm_receipt': str(arm_path),
              'boot_id': arm['boot_id'], 'packages': PACKAGES,
              'partition_scope': ['userdata Alpine ext4'],
              'boot_image_changed': False, 'wifi_restarted': False,
              'created_ns': time.time_ns()}

    def save():
        (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')

    def step(name, command, timeout=25):
        report['state'] = name + '-issued'; save()
        result = remote(command, timeout)
        (out / (name + '.stdout')).write_bytes(result.stdout)
        (out / (name + '.stderr')).write_bytes(result.stderr)
        if result.returncode:
            raise ValueError(name + ' failed; inspect captured streams')
        return result.stdout.decode(errors='replace')

    save()
    try:
        pre = step('preflight', '''set -eu
test "$(cat /proc/sys/kernel/random/boot_id)" = "''' + arm['boot_id'] + '''"
test "$(readlink /proc/1/exe)" = /run/lynx/persistent-alpine/sbin/openrc-init
grep -Eq '^/dev/sdc85 /run/lynx/persistent-alpine ext4 rw,' /proc/mounts
test ! -x /run/lynx/persistent-alpine/sbin/wpa_supplicant
netstat -lnt | grep ':22 '
netstat -lnt | grep ':2222 '
/bin/busybox sh /run/lynx/lynx-health-supervisor.sh --once
date -u +%s
''')
        if 'LYNX_HEALTH_OK ' not in pre:
            raise ValueError('Health preflight missing')
        if abs(int(pre.splitlines()[-1]) - int(time.time())) > 15:
            raise ValueError('Phone clock differs from Nexus')
        simulated = step('simulate', '/bin/busybox chroot /run/lynx/persistent-alpine /sbin/apk add --simulate ' + ' '.join(PACKAGES), 40)
        if 'wpa_supplicant' not in simulated or 'OK:' not in simulated:
            raise ValueError('Signed apk simulation differs')
        step('install', '/bin/busybox chroot /run/lynx/persistent-alpine /sbin/apk add ' + ' '.join(PACKAGES), 120)
        post = step('postcheck', '''set -eu
test "$(cat /proc/sys/kernel/random/boot_id)" = "''' + arm['boot_id'] + '''"
test -x /run/lynx/persistent-alpine/sbin/wpa_supplicant
test -x /run/lynx/persistent-alpine/sbin/wpa_cli
test -x /run/lynx/persistent-alpine/sbin/ip
/bin/busybox chroot /run/lynx/persistent-alpine /sbin/wpa_supplicant -v
/bin/busybox chroot /run/lynx/persistent-alpine /sbin/ip -V
netstat -lnt | grep ':22 '
netstat -lnt | grep ':2222 '
/bin/busybox sh /run/lynx/lynx-health-supervisor.sh --once
''')
        if 'LYNX_HEALTH_OK ' not in post:
            raise ValueError('Health postcheck missing')
        report['state'] = 'signed-alpine-wifi-installed-not-started'
    except Exception as error:
        report.update(state='failed-or-incomplete', error=str(error))
    report['finished_ns'] = time.time_ns(); save()
    print(json.dumps({'state': report['state'], 'result': str(out / 'result.json')}))
    if report['state'] != 'signed-alpine-wifi-installed-not-started':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
