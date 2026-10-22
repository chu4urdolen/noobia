"""Verify V45's same-boot local BusyBox-to-Alpine handoff over pinned SSH."""
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
IMAGE = ROOT / 'linux-port/artifacts/wifi-failure-code-v45-offline/nord3-wifi-failure-code-v45-untested.img'
IMAGE_SHA = '228b290e478649b7b7c48a865365771b73dbac73aaac361f73a245ddff24ca87'
INIT_SHA = '3d680e9ab78de5905dc86c6ffa5bb98e47ed15ee6b55da7d90bdedaa86a4343b'
BOOT_ID = re.compile(rb'(?m)^([0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})$')

SCRIPT = '''set -e
printf 'BOOT_ID='; cat /proc/sys/kernel/random/boot_id
printf 'INIT_SHA='; sha256sum /init
printf 'PID1_EXE='; readlink /proc/1/exe
printf 'PID1_ROOT='; readlink /proc/1/root
printf 'ALPINE_RELEASE='; cat /proc/1/root/etc/alpine-release
printf 'ROOT_MOUNT='; grep -E '^/dev/sdc85 /run/lynx/persistent-alpine ext4 rw,' /proc/mounts
test ! -e /run/lynx/host-confirmed
test ! -e /run/lynx/openrc-handoff-ready
printf 'LOCAL_READY='; cat /run/lynx/local-boot-ready
printf 'HANDOFF_LOG='; grep 'PERSISTENT_OPENRC_PID1_HANDOFF_BEGIN' /run/lynx/boot.log
printf 'LOCAL_GUARD='; cat /run/lynx/openrc-guard-last.log
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--collector', required=True, type=Path)
    args = parser.parse_args()
    path = args.collector.resolve(strict=True)
    if not path.is_relative_to(ROOT / 'logs'):
        raise ValueError('Collector outside Lynx logs')
    record = json.loads(path.read_text())
    if (record.get('image_sha256') != IMAGE_SHA or
            record.get('candidate_seen') is not True or
            record.get('alpine_pid1_seen') is not True or
            hashlib.sha256(IMAGE.read_bytes()).hexdigest() != IMAGE_SHA):
        raise ValueError('V45 image or same-boot collector proof missing')
    expected = None
    for index, sample in enumerate(record['samples'], 1):
        raw_path = path.parent / f'sample-{index}.raw'
        if not raw_path.exists() or sample.get('exit_code') != 0:
            continue
        raw = raw_path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != sample.get('sha256'):
            raise ValueError('Collector sample hash differs')
        if sample.get('v45_init_match') is True:
            match = BOOT_ID.search(raw)
            if match:
                expected = match.group(1).decode()
                break
    if not expected:
        raise ValueError('No exact V45 boot ID in collector')
    ip = record.get('pinned_ip') or next(
        (item['ip'] for item in reversed(record['samples']) if item.get('alpine_pid1_match')),
        None)
    if not re.fullmatch(r'192\.168\.100\.[1-9][0-9]?', ip or ''):
        raise ValueError('Pinned phone address differs')
    os.umask(0o077)
    out = ROOT / 'logs' / ('v45-autonomous-alpine-verification-' + str(time.time_ns()))
    out.mkdir(mode=0o700)
    result = {'state': 'starting', 'created_ns': time.time_ns(),
              'collector': str(path), 'boot_id': expected, 'phone_ip': ip,
              'image_sha256': IMAGE_SHA, 'phone_partition_writes': False}
    try:
        probe = subprocess.run(ssh_command(ip, SCRIPT), capture_output=True, timeout=30)
        (out / 'stdout').write_bytes(probe.stdout)
        (out / 'stderr').write_bytes(probe.stderr)
        data = probe.stdout.decode(errors='replace')
        required = [
            'BOOT_ID=' + expected + '\n',
            'INIT_SHA=' + INIT_SHA + '  /init\n',
            'PID1_EXE=/run/lynx/persistent-alpine/sbin/openrc-init\n',
            'PID1_ROOT=/run/lynx/persistent-alpine\n',
            'ALPINE_RELEASE=3.24.2\n',
            'ROOT_MOUNT=/dev/sdc85 /run/lynx/persistent-alpine ext4 rw,',
            'PERSISTENT_OPENRC_PID1_HANDOFF_BEGIN',
            'OPENRC_HANDOFF_GUARD_PASS ',
            'HEALTH_SERVICE_STATUS=0\n',
            'ALPINE_PYTHON=Python 3.',
            'ALPINE_GIT=git version ',
            'WIFI_ADDR=', 'SSH_LISTENER=', 'LYNX_HEALTH_OK ',
        ]
        if (probe.returncode or any(text not in data for text in required) or
                not re.search(r'(?m)^ lynx-health\s+\[\s*started\s*\]', data)):
            raise ValueError('Autonomous Alpine/OpenRC, Wi-Fi or health proof refused')
        result.update(state='autonomous-alpine-pid1-verified',
                      ssh_exit_code=probe.returncode,
                      stdout_sha256=hashlib.sha256(probe.stdout).hexdigest())
    except Exception as error:
        result.update(state='failed-or-incomplete', error=str(error))
    result['finished_ns'] = time.time_ns()
    receipt = out / 'result.json'
    receipt.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'state': result['state'], 'result': str(receipt)}))
    if result['state'] != 'autonomous-alpine-pid1-verified':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
