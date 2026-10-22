"""Verify V46's same-boot autonomous Alpine handoff over pinned Wi-Fi SSH."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time

from lynx_wifi_v19_contact import ssh_command
from verify_autonomous_alpine_v45 import BOOT_ID, SCRIPT

ROOT = Path(__file__).resolve().parent.parent
IMAGE = ROOT / 'linux-port/artifacts/persistent-alpine-v46-offline/nord3-persistent-alpine-v46-untested.img'
BUILD = IMAGE.parent / 'build-result.json'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--collector', required=True, type=Path)
    args = parser.parse_args()
    path = args.collector.resolve(strict=True)
    if not path.is_relative_to(ROOT / 'logs'):
        raise ValueError('Collector outside Lynx logs')
    record = json.loads(path.read_text())
    build = json.loads(BUILD.read_text())
    image_sha, init_sha = build['image_sha256'], build['init_sha256']
    if (record.get('image_sha256') != image_sha or
            record.get('candidate_seen') is not True or
            record.get('alpine_pid1_seen') is not True or
            hashlib.sha256(IMAGE.read_bytes()).hexdigest() != image_sha):
        raise ValueError('V46 image or same-boot collector proof missing')
    expected = None
    for index, sample in enumerate(record['samples'], 1):
        raw_path = path.parent / f'sample-{index}.raw'
        if not raw_path.exists() or sample.get('exit_code') != 0:
            continue
        raw = raw_path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != sample.get('sha256'):
            raise ValueError('Collector sample hash differs')
        if sample.get('v46_init_match') is True:
            match = BOOT_ID.search(raw)
            if match:
                expected = match.group(1).decode()
                break
    if not expected:
        raise ValueError('No exact V46 boot ID in collector')
    ip = record.get('pinned_ip') or next(
        (item['ip'] for item in reversed(record['samples']) if item.get('alpine_pid1_match')),
        None)
    if not re.fullmatch(r'192\.168\.100\.[1-9][0-9]?', ip or ''):
        raise ValueError('Pinned phone address differs')
    os.umask(0o077)
    out = ROOT / 'logs' / ('v46-autonomous-alpine-verification-' + str(time.time_ns()))
    out.mkdir(mode=0o700)
    result = {'state': 'starting', 'created_ns': time.time_ns(),
              'collector': str(path), 'boot_id': expected, 'phone_ip': ip,
              'image_sha256': image_sha, 'phone_partition_writes': False}
    try:
        probe = subprocess.run(ssh_command(ip, SCRIPT), capture_output=True, timeout=30)
        (out / 'stdout').write_bytes(probe.stdout)
        (out / 'stderr').write_bytes(probe.stderr)
        data = probe.stdout.decode(errors='replace')
        required = [
            'BOOT_ID=' + expected + '\n',
            'INIT_SHA=' + init_sha + '  /init\n',
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
        if (probe.returncode or any(value not in data for value in required) or
                not re.search(r'(?m)^ lynx-health\s+\[\s*started\s*\]', data)):
            raise ValueError('Autonomous Alpine/OpenRC, Wi-Fi or health proof refused')
        result.update(state='v46-autonomous-alpine-pid1-verified',
                      ssh_exit_code=probe.returncode,
                      stdout_sha256=hashlib.sha256(probe.stdout).hexdigest())
    except Exception as error:
        result.update(state='failed-or-incomplete', error=str(error))
    result['finished_ns'] = time.time_ns()
    receipt = out / 'result.json'
    receipt.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'state': result['state'], 'result': str(receipt)}))
    if result['state'] != 'v46-autonomous-alpine-pid1-verified':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
