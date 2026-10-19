"""Start Alpine's signed Dropbear on port 2222 without touching rescue SSH 22.

Copies Lynx's existing private host key and authorized public key into the
persistent Alpine root with restrictive modes. No key contents are logged.
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import time

from lynx_wifi_v19_contact import ssh_command

ROOT = Path(__file__).resolve().parent.parent
IP = '192.168.100.4'


def receipt(path):
    path = path.resolve(strict=True)
    if not path.is_relative_to(ROOT / 'logs'):
        raise ValueError('Receipt outside Lynx logs')
    return json.loads(path.read_text()), str(path)


def remote(command, timeout=20, port=22):
    argv = ssh_command(IP, command)
    if port != 22:
        argv[-2:-2] = ['-p', str(port)]
    return subprocess.run(argv, capture_output=True, timeout=timeout)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--arm-receipt', required=True, type=Path)
    parser.add_argument('--install-receipt', required=True, type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--trial', action='store_true')
    mode.add_argument('--verify-existing', action='store_true')
    args = parser.parse_args()
    arm, arm_path = receipt(args.arm_receipt)
    installed, installed_path = receipt(args.install_receipt)
    if (arm.get('state') != 'v33-openrc-armed' or
            installed.get('state') != 'signed-dropbear-installed-service-held' or
            installed.get('arm_receipt') != arm_path or
            installed.get('boot_id') != arm.get('boot_id')):
        raise ValueError('Same-boot Alpine/Dropbear receipts differ')
    if not args.trial and not args.verify_existing:
        print(json.dumps({'state': 'trial-held', 'phone_contacted': False,
                          'rescue_ssh_port': 22, 'alpine_trial_port': 2222}))
        return
    os.umask(0o077)
    out = ROOT / 'logs' / ('alpine-dropbear-2222-trial-' + str(time.time_ns()))
    out.mkdir(mode=0o700)
    report = {'state': 'starting', 'arm_receipt': arm_path,
              'install_receipt': installed_path, 'boot_id': arm['boot_id'],
              'phone_partition_writes': ['Alpine root SSH key/config files'],
              'rescue_ssh_port': 22, 'alpine_trial_port': 2222,
              'openrc_service_enabled': False, 'created_ns': time.time_ns()}
    def step(name, command, timeout=20, port=22):
        report['state'] = name + '-issued'
        (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
        result = remote(command, timeout=timeout, port=port)
        (out / (name + '.stdout')).write_bytes(result.stdout)
        (out / (name + '.stderr')).write_bytes(result.stderr)
        if result.returncode:
            raise ValueError(name + ' refused; inspect captured streams')
        return result.stdout.decode(errors='replace')
    try:
        if args.trial:
            pre = step('preflight', '''set -eu
test "$(cat /proc/sys/kernel/random/boot_id)" = "''' + arm['boot_id'] + '''"
test "$(readlink /proc/1/exe)" = /run/lynx/persistent-alpine/sbin/openrc-init
test -x /run/lynx/persistent-alpine/usr/sbin/dropbear
test -r /etc/dropbear/lynx_ed25519_host_key
test -r /root/.ssh/authorized_keys
! netstat -lnt | grep -q ':2222 '
netstat -lnt | grep ':22 '
/bin/busybox sh /run/lynx/lynx-health-supervisor.sh --once
''')
            if 'LYNX_HEALTH_OK ' not in pre:
                raise ValueError('Health preflight missing')
            step('stage-credentials', '''set -eu
umask 077
root=/run/lynx/persistent-alpine
mkdir -m 700 -p "$root/root/.ssh" "$root/etc/dropbear"
cp /root/.ssh/authorized_keys "$root/root/.ssh/authorized_keys"
cp /etc/dropbear/lynx_ed25519_host_key "$root/etc/dropbear/lynx_ed25519_host_key"
chmod 700 "$root/root/.ssh"
chmod 600 "$root/root/.ssh/authorized_keys" "$root/etc/dropbear/lynx_ed25519_host_key"
cmp -s /root/.ssh/authorized_keys "$root/root/.ssh/authorized_keys"
cmp -s /etc/dropbear/lynx_ed25519_host_key "$root/etc/dropbear/lynx_ed25519_host_key"
echo ALPINE_SSH_CREDENTIALS_STAGED
''')
            launched = step('launch', '''set -eu
test "$(cat /proc/sys/kernel/random/boot_id)" = "''' + arm['boot_id'] + '''"
! netstat -lnt | grep -q ':2222 '
/bin/busybox chroot /run/lynx/persistent-alpine /usr/sbin/dropbear -E -s -j -k -p 192.168.100.4:2222 -P /run/lynx/alpine-dropbear-2222.pid -r /etc/dropbear/lynx_ed25519_host_key </dev/null >>/run/lynx/alpine-dropbear-2222.log 2>&1
sleep 1
test -r /run/lynx/alpine-dropbear-2222.pid
kill -0 "$(cat /run/lynx/alpine-dropbear-2222.pid)"
netstat -lnt | grep ':2222 '
netstat -lnt | grep ':22 '
echo ALPINE_DROPBEAR_2222_LISTENING
''')
            if 'ALPINE_DROPBEAR_2222_LISTENING' not in launched:
                raise ValueError('New listener not confirmed')
        else:
            step('existing-listeners', '''set -eu
test "$(cat /proc/sys/kernel/random/boot_id)" = "''' + arm['boot_id'] + '''"
test "$(readlink /proc/1/exe)" = /run/lynx/persistent-alpine/sbin/openrc-init
test -r /run/lynx/alpine-dropbear-2222.pid
kill -0 "$(cat /run/lynx/alpine-dropbear-2222.pid)"
netstat -lnt | grep ':22 '
netstat -lnt | grep ':2222 '
/bin/busybox sh /run/lynx/lynx-health-supervisor.sh --once
''')
        proof = step('alpine-ssh-proof', '''set -eu
test "$(cat /proc/sys/kernel/random/boot_id)" = "''' + arm['boot_id'] + '''"
test "$(cat /etc/alpine-release)" = 3.24.2
test "$(readlink /proc/1/exe)" = /sbin/openrc-init
id
echo ALPINE_NATIVE_SSH_2222_VERIFIED
''', port=2222)
        if not re.search(r'uid=0\(root\)', proof) or 'ALPINE_NATIVE_SSH_2222_VERIFIED' not in proof:
            raise ValueError('Alpine SSH identity differs')
        report['state'] = 'alpine-dropbear-2222-verified'
    except Exception as error:
        report.update(state='failed-or-incomplete', error=str(error))
    report['finished_ns'] = time.time_ns()
    (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'state': report['state'], 'result': str(out / 'result.json')}))
    if report['state'] != 'alpine-dropbear-2222-verified':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
