"""Stage Lynx's Alpine Wi-Fi service and private config, then adopt or enable.

Current network processes are not stopped or restarted. Secret Wi-Fi config
stays on the phone; logs record only checks, never its contents or hash.
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
SOURCE = ROOT / 'linux-port/lynx-wifi-openrc.sh'
IP = '192.168.100.4'


def load(path):
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
    parser.add_argument('--install-receipt', required=True, type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--stage-and-start', action='store_true')
    mode.add_argument('--enable', action='store_true')
    args = parser.parse_args()
    arm, arm_path = load(args.arm_receipt)
    installed, installed_path = load(args.install_receipt)
    if (arm.get('state') != 'v33-openrc-armed' or
            installed.get('state') != 'signed-alpine-wifi-installed-not-started' or
            installed.get('arm_receipt') != arm_path or
            installed.get('boot_id') != arm.get('boot_id')):
        raise ValueError('Same-boot Alpine Wi-Fi evidence differs')
    source = SOURCE.read_bytes()
    digest = hashlib.sha256(source).hexdigest()
    if not (args.stage_and_start or args.enable):
        print(json.dumps({'state': 'held', 'source_sha256': digest,
                          'phone_contacted': False, 'partition_writes': False}))
        return
    os.umask(0o077)
    out = ROOT / 'logs' / ('alpine-wifi-openrc-' + str(time.time_ns()))
    out.mkdir(mode=0o700)
    report = {'state': 'starting', 'mode': 'stage-and-start' if args.stage_and_start else 'enable',
              'arm_receipt': arm_path, 'install_receipt': installed_path,
              'boot_id': arm['boot_id'], 'service_sha256': digest,
              'partition_scope': ['Alpine ext4 /etc/lynx and OpenRC service/runlevel'],
              'boot_image_changed': False, 'rescue_wifi_not_restarted': True,
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
test "$(cat /sys/class/net/wlan0/carrier)" = 1
netstat -lnt | grep ':22 '
netstat -lnt | grep ':2222 '
/bin/busybox sh /run/lynx/lynx-health-supervisor.sh --once
''')
        if 'LYNX_HEALTH_OK ' not in pre:
            raise ValueError('Health preflight missing')
        root = '/run/lynx/persistent-alpine'
        target = root + '/etc/init.d/lynx-wifi'
        config = root + '/etc/lynx/wpa_supplicant.conf'
        if args.stage_and_start:
            step('require-new-targets', 'test ! -e ' + target + ' && test ! -e ' + config)
            # The source file never traverses the Nexus or any diagnostic stream.
            step('copy-private-config', '''set -eu
install -d -m 700 ''' + root + '''/etc/lynx
cp /etc/lynx/wpa_supplicant.conf ''' + config + '''.tmp
chmod 600 ''' + config + '''.tmp
cmp -s /etc/lynx/wpa_supplicant.conf ''' + config + '''.tmp
mv ''' + config + '''.tmp ''' + config + '''
test "$(stat -c %a ''' + config + ''')" = 600
''')
            step('upload-service', 'cat > ' + target + '.tmp', data=source)
            checked = step('verify-upload', 'sha256sum ' + target + '.tmp')
            if checked.strip() != digest + '  ' + target + '.tmp':
                raise ValueError('Service upload hash differs')
            step('install-service', 'chmod 755 ' + target + '.tmp && mv ' + target + '.tmp ' + target)
            adopted = step('adopt-connection', '''set -eu
before=$(cat /proc/sys/kernel/random/boot_id)
/bin/busybox chroot ''' + root + ''' /sbin/rc-service lynx-wifi start
/bin/busybox chroot ''' + root + ''' /sbin/rc-service lynx-wifi status
test "$(cat /proc/sys/kernel/random/boot_id)" = "$before"
netstat -lnt | grep ':22 '
netstat -lnt | grep ':2222 '
echo LYNX_WIFI_OPENRC_ADOPTED
''', timeout=30)
            if 'LYNX_WIFI_OPENRC_ADOPTED' not in adopted:
                raise ValueError('WLAN adoption marker missing')
            report['state'] = 'alpine-wifi-service-adopted'
        else:
            step('verify-service', '''set -eu
test -x ''' + target + '''
test -s ''' + config + '''
/bin/busybox chroot ''' + root + ''' /sbin/rc-service lynx-wifi status
''')
            enabled = step('enable-default', '''set -eu
/bin/busybox chroot ''' + root + ''' /sbin/rc-update add lynx-wifi default
test "$(readlink ''' + root + '''/etc/runlevels/default/lynx-wifi)" = /etc/init.d/lynx-wifi
netstat -lnt | grep ':22 '
netstat -lnt | grep ':2222 '
echo LYNX_WIFI_OPENRC_ENABLED
''')
            if 'LYNX_WIFI_OPENRC_ENABLED' not in enabled:
                raise ValueError('Runlevel marker missing')
            report['state'] = 'alpine-wifi-service-enabled'
    except Exception as error:
        report.update(state='failed-or-incomplete', error=str(error))
    report['finished_ns'] = time.time_ns(); save()
    print(json.dumps({'state': report['state'], 'result': str(out / 'result.json')}))
    if report['state'] not in ('alpine-wifi-service-adopted', 'alpine-wifi-service-enabled'):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
