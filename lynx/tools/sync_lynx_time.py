"""Set Lynx's volatile system clock from NTP-synchronized Nexus time.

This changes only the running clock. It does not write partitions, configure
RTC, contact an external time service from Lynx, or change boot images.
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


def remote(command):
    return subprocess.run(ssh_command(IP, command), capture_output=True, timeout=15)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--arm-receipt', required=True, type=Path)
    parser.add_argument('--set', action='store_true')
    args = parser.parse_args()
    arm_path = args.arm_receipt.resolve(strict=True)
    if not arm_path.is_relative_to(ROOT / 'logs'):
        raise ValueError('Arm receipt outside Lynx logs')
    arm = json.loads(arm_path.read_text())
    if arm.get('state') != 'v33-openrc-armed':
        raise ValueError('V33 arm receipt refused')
    ntp = subprocess.run(['timedatectl', 'show', '-p', 'NTPSynchronized', '--value'],
                         capture_output=True, text=True, timeout=10)
    if ntp.returncode or ntp.stdout.strip() != 'yes':
        raise ValueError('Nexus clock is not reported NTP-synchronized')
    if not args.set:
        print(json.dumps({'state': 'host-time-ready', 'host_epoch': int(time.time()),
                          'phone_contacted': False, 'clock_changed': False}))
        return
    os.umask(0o077)
    out = ROOT / 'logs' / ('lynx-time-sync-' + str(time.time_ns()))
    out.mkdir(mode=0o700)
    report = {'state': 'starting', 'arm_receipt': str(arm_path),
              'boot_id': arm['boot_id'], 'phone_partition_writes': False,
              'clock_changed': False, 'created_ns': time.time_ns()}
    try:
        pre = remote('''set -eu
test "$(cat /proc/sys/kernel/random/boot_id)" = "''' + arm['boot_id'] + '''"
test "$(readlink /proc/1/exe)" = /run/lynx/persistent-alpine/sbin/openrc-init
/bin/busybox sh /run/lynx/lynx-health-supervisor.sh --once
date -u +%s
''')
        (out / 'pre.stdout').write_bytes(pre.stdout)
        (out / 'pre.stderr').write_bytes(pre.stderr)
        if pre.returncode or b'LYNX_HEALTH_OK ' not in pre.stdout:
            raise ValueError('Same-boot Alpine health preflight refused')
        epoch = int(time.time())
        report['source_host_epoch'] = epoch
        report['state'] = 'clock-set-issued'
        (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
        setting = remote('/bin/busybox date -u -s @' + str(epoch))
        (out / 'set.stdout').write_bytes(setting.stdout)
        (out / 'set.stderr').write_bytes(setting.stderr)
        if setting.returncode:
            raise ValueError('BusyBox clock set refused')
        report['clock_changed'] = True
        post = remote('''set -eu
test "$(cat /proc/sys/kernel/random/boot_id)" = "''' + arm['boot_id'] + '''"
date -u +%s
/bin/busybox sh /run/lynx/lynx-health-supervisor.sh --once
''')
        (out / 'post.stdout').write_bytes(post.stdout)
        (out / 'post.stderr').write_bytes(post.stderr)
        if post.returncode or b'LYNX_HEALTH_OK ' not in post.stdout:
            raise ValueError('Clock postcheck or health refused')
        phone_epoch = int(post.stdout.decode().splitlines()[0])
        delta = abs(phone_epoch - int(time.time()))
        report.update(phone_epoch=phone_epoch, host_delta_seconds=delta)
        if delta > 10:
            raise ValueError('Phone/host clock difference exceeds 10 seconds')
        report['state'] = 'volatile-clock-synchronized'
    except Exception as error:
        report.update(state='failed-or-incomplete', error=str(error))
    report['finished_ns'] = time.time_ns()
    (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'state': report['state'], 'result': str(out / 'result.json')}))
    if report['state'] != 'volatile-clock-synchronized':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
