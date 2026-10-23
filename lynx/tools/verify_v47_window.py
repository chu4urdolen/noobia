"""Verify V47 Alpine survives beyond V45's old 420-second timer boundary."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import time


ROOT = Path(__file__).resolve().parent.parent
IMAGE_SHA = 'c969e1938b051ab03b49ad4f2260e900e9e336997d1026ca00c3a493dedde066'


def receipt(path):
    path = path.resolve(strict=True)
    if not path.is_relative_to(ROOT / 'logs'):
        raise ValueError('Receipt outside Lynx logs')
    return path, json.loads(path.read_text())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--collector', required=True, type=Path)
    parser.add_argument('--verification', required=True, type=Path)
    args = parser.parse_args()
    (path, collector), (vpath, verified) = map(receipt, (args.collector,
                                                         args.verification))
    boot_id = verified.get('boot_id')
    if (collector.get('image_sha256') != IMAGE_SHA or
            verified.get('state') != 'v47-alpine-and-recovery-verified' or
            verified.get('image_sha256') != IMAGE_SHA or
            not collector.get('candidate_seen') or
            not collector.get('alpine_pid1_seen') or
            not re.fullmatch(r'[0-9a-f-]{36}', str(boot_id))):
        raise ValueError('V47 collector or live verification differs')
    complete = []
    for index, item in enumerate(collector['samples'], 1):
        filename = path.parent / f'sample-{index}.raw'
        if not filename.is_file():
            continue
        raw = filename.read_bytes()
        if hashlib.sha256(raw).hexdigest() != item.get('sha256'):
            continue
        if not (item.get('exit_code') == 0 and item.get('init_match') and
                item.get('wifi_match') and item.get('alpine_pid1_match')):
            continue
        if f'BOOT_ID={boot_id}\n'.encode() not in raw:
            continue
        match = re.search(rb'^UPTIME=(\d+)\.\d+', raw, re.M)
        if not match:
            continue
        complete.append((index, int(match.group(1))))
    if not complete:
        raise ValueError('No verified Alpine sample')
    max_uptime = max(value for _, value in complete)
    finished = [(index, item) for index, item in enumerate(collector['samples'], 1)
                if 'exit_code' in item or item.get('timed_out')]
    last_index, last = finished[-1]
    last_healthy = (last.get('alpine_pid1_match') and last.get('wifi_match') and
                    last.get('exit_code') == 0 and
                    complete[-1][0] == last_index)
    passed = (len(complete) >= 10 and max_uptime >= 450 and last_healthy)
    os.umask(0o077)
    out = ROOT / 'logs' / f'v47-window-verification-{time.time_ns()}.json'
    report = {'state': 'v47-alpine-past-old-timer-verified' if passed
              else 'failed-or-incomplete', 'boot_id': boot_id,
              'collector': str(path), 'verification': str(vpath),
              'alpine_samples': len(complete), 'max_uptime_seconds': max_uptime,
              'last_sample_healthy': bool(last_healthy), 'phone_contacted': False,
              'phone_writes': False}
    out.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'state': report['state'], 'result': str(out),
                      'max_uptime_seconds': max_uptime}))
    if not passed:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
