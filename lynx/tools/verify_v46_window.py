"""Verify the completed V46 SSH window stayed on one Alpine boot past V45's timer."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import time

ROOT = Path(__file__).resolve().parent.parent
BOOT_ID = re.compile(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--collector', type=Path, required=True)
    args = parser.parse_args()
    path = args.collector.resolve(strict=True)
    if not path.is_relative_to(ROOT / 'logs'):
        raise ValueError('Collector outside Lynx logs')
    record = json.loads(path.read_text())
    build = json.loads((ROOT / 'linux-port/artifacts/persistent-alpine-v46-offline/build-result.json').read_text())
    if (record['state'] != 'deadline' or record['image_sha256'] != build['image_sha256'] or
            record['candidate_seen'] is not True or record['alpine_pid1_seen'] is not True):
        raise ValueError('Completed exact V46 collector missing')
    complete = []
    incomplete = []
    for index, item in enumerate(record['samples'], 1):
        if item.get('exit_code') != 0:
            incomplete.append(index)
            continue
        raw_path = path.parent / f'sample-{index}.raw'
        raw = raw_path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != item['sha256']:
            raise ValueError(f'Sample {index} hash differs')
        lines = raw.decode(errors='replace').splitlines()
        if len(lines) < 8 or not BOOT_ID.fullmatch(lines[5]):
            raise ValueError(f'Sample {index} boot identity malformed')
        uptime = float(lines[4].split()[0])
        complete.append({'index': index, 'boot_id': lines[5], 'uptime_seconds': uptime,
                         'v46_init_match': item.get('v46_init_match') is True,
                         'alpine_pid1_match': item.get('alpine_pid1_match') is True})
    ids = {sample['boot_id'] for sample in complete}
    alpine = [sample for sample in complete if sample['alpine_pid1_match']]
    if (len(ids) != 1 or not complete or not alpine or
            not any(sample['v46_init_match'] for sample in complete) or
            alpine[-1]['uptime_seconds'] <= 600 or
            any(right['uptime_seconds'] < left['uptime_seconds']
                for left, right in zip(complete, complete[1:]))):
        raise ValueError('Same-boot V46 sustained Alpine proof missing')
    os.umask(0o077)
    out = ROOT / 'logs' / ('v46-window-verification-' + str(time.time_ns()) + '.json')
    result = {'state': 'v46-sustained-alpine-window-verified',
              'collector': str(path), 'boot_id': next(iter(ids)),
              'complete_samples': len(complete), 'incomplete_samples': incomplete,
              'first_alpine_uptime_seconds': alpine[0]['uptime_seconds'],
              'last_alpine_uptime_seconds': alpine[-1]['uptime_seconds'],
              'sample_hashes_verified': True, 'phone_contacted': False}
    out.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'state': result['state'], 'result': str(out),
                      'last_alpine_uptime_seconds': result['last_alpine_uptime_seconds']}))


if __name__ == '__main__':
    main()
