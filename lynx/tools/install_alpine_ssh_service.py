"""Stage and adopt Lynx's Alpine SSH OpenRC service, then optionally enable it.

Uses the verified port-2222 process without touching rescue SSH port 22.
Persistent writes are confined to Alpine's ext4 root.
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
SOURCE = ROOT / 'linux-port/lynx-dropbear-openrc.sh'
IP = '192.168.100.4'


def receipt(path):
    path = path.resolve(strict=True)
    if not path.is_relative_to(ROOT / 'logs'):
        raise ValueError('Receipt outside Lynx logs')
    return json.loads(path.read_text()), str(path)


def remote(command, data=None, timeout=20):
    return subprocess.run(ssh_command(IP, command), input=data,
                          capture_output=True, timeout=timeout)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--arm-receipt', required=True, type=Path)
    parser.add_argument('--alpine-ssh-receipt', required=True, type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--install-and-start', action='store_true')
    mode.add_argument('--enable', action='store_true')
    args = parser.parse_args()
    arm, arm_path = receipt(args.arm_receipt)
    ssh, ssh_path = receipt(args.alpine_ssh_receipt)
    if (arm.get('state') != 'v33-openrc-armed' or
            ssh.get('state') != 'alpine-dropbear-2222-verified' or
            ssh.get('arm_receipt') != arm_path or
            ssh.get('boot_id') != arm.get('boot_id')):
        raise ValueError('Same-boot Alpine SSH evidence differs')
    source = SOURCE.read_bytes()
    digest = hashlib.sha256(source).hexdigest()
    if not (args.install_and_start or args.enable):
        print(json.dumps({'state': 'service-held', 'source_sha256': digest,
                          'phone_contacted': False, 'partition_writes': False}))
        return
    os.umask(0o077)
    out = ROOT / 'logs' / ('alpine-ssh-openrc-' + str(time.time_ns()))
    out.mkdir(mode=0o700)
    report = {'state': 'starting', 'mode': 'install-and-start' if args.install_and_start else 'enable',
              'arm_receipt': arm_path, 'alpine_ssh_receipt': ssh_path,
              'boot_id': arm['boot_id'], 'source_sha256': digest,
              'partition_scope': ['Alpine ext4 /etc/init.d and runlevel symlink'],
              'boot_image_changed': False, 'rescue_ssh_port_untouched': True,
              'created_ns': time.time_ns()}
    def save():
        (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    def step(name, command, data=None, timeout=20):
        report['state'] = name + '-issued'; save()
        result = remote(command, data=data, timeout=timeout)
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
netstat -lnt | grep ':22 '
netstat -lnt | grep ':2222 '
/bin/busybox sh /run/lynx/lynx-health-supervisor.sh --once
''')
        if 'LYNX_HEALTH_OK ' not in pre:
            raise ValueError('Health preflight missing')
        target = '/run/lynx/persistent-alpine/etc/init.d/lynx-dropbear'
        if args.install_and_start:
            step('require-new-target', 'test ! -e ' + target)
            step('upload', 'cat > ' + target + '.tmp', data=source)
            checked = step('verify-upload', 'sha256sum ' + target + '.tmp')
            if checked.strip() != digest + '  ' + target + '.tmp':
                raise ValueError('Uploaded service hash differs')
            step('install', 'chmod 755 ' + target + '.tmp && mv ' + target + '.tmp ' + target)
            started = step('adopt-process', '''set -eu
before=$(cat /run/lynx/alpine-dropbear-2222.pid)
/bin/busybox chroot /run/lynx/persistent-alpine /sbin/rc-service lynx-dropbear start
/bin/busybox chroot /run/lynx/persistent-alpine /sbin/rc-service lynx-dropbear status
test "$(cat /run/lynx/alpine-dropbear-2222.pid)" = "$before"
netstat -lnt | grep ':22 '
netstat -lnt | grep ':2222 '
echo LYNX_ALPINE_SSH_OPENRC_ADOPTED
''', timeout=30)
            if 'LYNX_ALPINE_SSH_OPENRC_ADOPTED' not in started:
                raise ValueError('OpenRC adoption marker missing')
            report['state'] = 'alpine-ssh-service-started'
        else:
            step('verify-service', '''set -eu
/bin/busybox chroot /run/lynx/persistent-alpine /sbin/rc-service lynx-dropbear status
test -x ''' + target + '''
''')
            enabled = step('enable-default', '''set -eu
/bin/busybox chroot /run/lynx/persistent-alpine /sbin/rc-update add lynx-dropbear default
test "$(readlink /run/lynx/persistent-alpine/etc/runlevels/default/lynx-dropbear)" = /etc/init.d/lynx-dropbear
netstat -lnt | grep ':22 '
netstat -lnt | grep ':2222 '
echo LYNX_ALPINE_SSH_ENABLED_DEFAULT
''')
            if 'LYNX_ALPINE_SSH_ENABLED_DEFAULT' not in enabled:
                raise ValueError('Default runlevel marker missing')
            report['state'] = 'alpine-ssh-service-enabled'
    except Exception as error:
        report.update(state='failed-or-incomplete', error=str(error))
    report['finished_ns'] = time.time_ns(); save()
    print(json.dumps({'state': report['state'], 'result': str(out / 'result.json')}))
    if report['state'] not in ('alpine-ssh-service-started', 'alpine-ssh-service-enabled'):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
