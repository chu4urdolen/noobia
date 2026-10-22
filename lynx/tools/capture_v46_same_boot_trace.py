"""Read and checksum-validate V46's persistent stage record for one verified boot."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time

from lynx_wifi_v19_contact import ssh_command
from parse_v38_persistent_trace import parse

ROOT = Path(__file__).resolve().parent.parent
BOOT_ID = re.compile(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verification', required=True, type=Path)
    args = parser.parse_args()
    path = args.verification.resolve(strict=True)
    if not path.is_relative_to(ROOT / 'logs'):
        raise ValueError('Verification outside Lynx logs')
    verified = json.loads(path.read_text())
    boot_id, ip = verified['boot_id'], verified['phone_ip']
    if (verified['state'] != 'v46-autonomous-alpine-pid1-verified' or
            not BOOT_ID.fullmatch(boot_id) or
            not re.fullmatch(r'192\.168\.100\.[1-9][0-9]?', ip)):
        raise ValueError('Same-boot V46 verification missing')
    build = json.loads((ROOT / 'linux-port/artifacts/persistent-alpine-v46-offline/build-result.json').read_text())
    if verified['image_sha256'] != build['image_sha256']:
        raise ValueError('Image identity differs')
    init_sha = build['init_sha256']
    remote = ("set -eu; test \"$(cat /proc/sys/kernel/random/boot_id)\" = '" + boot_id +
              "'; test \"$(sha256sum /init | cut -d ' ' -f 1)\" = '" + init_sha +
              "'; cat '/run/lynx/persistent-alpine/var/log/lynx-bootdiag/" + boot_id + ".log'")
    os.umask(0o077)
    out = ROOT / 'logs' / ('v46-same-boot-stage-' + str(time.time_ns()))
    out.mkdir(mode=0o700)
    result = {'state': 'starting', 'created_ns': time.time_ns(),
              'verification': str(path), 'boot_id': boot_id, 'phone_ip': ip,
              'phone_partition_writes': False}
    try:
        probe = subprocess.run(ssh_command(ip, remote), capture_output=True, timeout=15)
        (out / 'stderr').write_bytes(probe.stderr)
        record = out / (boot_id + '.log')
        record.write_bytes(probe.stdout)
        if probe.returncode or not 1 <= record.stat().st_size <= 4096:
            raise ValueError('Same-boot read failed or exceeded bound')
        parsed = parse(record)
        stages = [event['stage'] for event in parsed['events']]
        if not all(stage in stages for stage in ('HEALTH_READY', 'HANDOFF_BEGIN', 'TIMER_CANCELLED')):
            raise ValueError('Handoff and timer-cancellation stages incomplete')
        result.update(state='v46-timer-cancellation-record-verified',
                      record=parsed, raw_sha256=hashlib.sha256(probe.stdout).hexdigest())
    except Exception as error:
        result.update(state='failed-or-incomplete', error=str(error))
    result['finished_ns'] = time.time_ns()
    receipt = out / 'result.json'
    receipt.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'state': result['state'], 'result': str(receipt)}))
    if result['state'] != 'v46-timer-cancellation-record-verified':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
