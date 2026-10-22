"""Verify a supervised V46 OpenRC reboot reached sustained autonomous Alpine."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import time

ROOT = Path(__file__).resolve().parent.parent
BOOT_ID = re.compile(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}')


def receipt(path):
    path = path.resolve(strict=True)
    if not path.is_relative_to(ROOT / 'logs'):
        raise ValueError('Receipt outside Lynx logs')
    return json.loads(path.read_text()), str(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('reboot', 'collector', 'verification', 'stage', 'native_ssh'):
        parser.add_argument('--' + name.replace('_', '-'), type=Path, required=True)
    args = parser.parse_args()
    reboot, reboot_path = receipt(args.reboot)
    collected, collector_path = receipt(args.collector)
    verified, verification_path = receipt(args.verification)
    stage, stage_path = receipt(args.stage)
    native, native_path = receipt(args.native_ssh)
    old, new = reboot['old_boot_id'], verified['boot_id']
    if (reboot['state'] != 'reboot-command-sent' or
            verified['state'] != 'v46-autonomous-alpine-pid1-verified' or
            stage['state'] != 'v46-timer-cancellation-record-verified' or
            native['state'] != 'v46-alpine-native-ssh-verified' or
            collected['state'] != 'interrupted' or
            not BOOT_ID.fullmatch(old) or not BOOT_ID.fullmatch(new) or old == new or
            verified['collector'] != collector_path or
            stage['verification'] != verification_path or
            native['verification'] != verification_path or
            stage['boot_id'] != new or native['boot_id'] != new or
            len({reboot['image_sha256'], verified['image_sha256'],
                 collected['image_sha256']}) != 1):
        raise ValueError('Reboot and same-boot proof receipts differ')
    complete = []
    for index, sample in enumerate(collected['samples'], 1):
        if sample.get('exit_code') != 0:
            raise ValueError(f'Incomplete sample {index}')
        raw = (Path(collector_path).parent / f'sample-{index}.raw').read_bytes()
        if hashlib.sha256(raw).hexdigest() != sample['sha256']:
            raise ValueError(f'Sample {index} hash differs')
        lines = raw.decode(errors='replace').splitlines()
        if len(lines) < 8 or lines[5] != new:
            raise ValueError(f'Sample {index} new boot ID differs')
        complete.append((float(lines[4].split()[0]), sample.get('alpine_pid1_match') is True))
    alpine = [uptime for uptime, matched in complete if matched]
    if (not complete or not alpine or alpine[-1] <= 428 or
            any(right[0] < left[0] for left, right in zip(complete, complete[1:]))):
        raise ValueError('New boot did not reach Alpine beyond old timer')
    stages = [item['stage'] for item in stage['record']['events']]
    if not all(item in stages for item in ('HEALTH_READY', 'HANDOFF_BEGIN', 'TIMER_CANCELLED')):
        raise ValueError('New boot stage proof differs')
    os.umask(0o077)
    output = ROOT / 'logs' / ('v46-reboot-verification-' + str(time.time_ns()) + '.json')
    result = {'state': 'v46-autonomous-warm-reboot-verified',
              'reboot_receipt': reboot_path, 'collector_receipt': collector_path,
              'verification_receipt': verification_path, 'stage_receipt': stage_path,
              'native_ssh_receipt': native_path, 'old_boot_id': old,
              'new_boot_id': new, 'complete_same_boot_samples': len(complete),
              'first_alpine_uptime_seconds': alpine[0],
              'last_alpine_uptime_seconds': alpine[-1],
              'sample_hashes_verified': True, 'phone_contacted': False}
    output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'state': result['state'], 'result': str(output),
                      'last_alpine_uptime_seconds': result['last_alpine_uptime_seconds']}))


if __name__ == '__main__':
    main()
