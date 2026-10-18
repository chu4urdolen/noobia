"""Compare bounded, read-only Lynx expdb captures without exposing raw logs.

The useful stock LK regions are in the first 0xF0000 bytes: SYS_RAMCONSOLE_RAW
at 0x2000..0x2fff and SYS_PSTORE_RAW at 0x3000..0xeffff. Accept a full 128 MiB
baseline or a 0xF0000 capture, but compare only that documented prefix.
"""
import argparse
import hashlib
import json
import os
import re
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIMIT = 0xF0000
BLOCK = 4096
REGIONS = {
    'ramconsole': (0x2000, 0x3000),
    'pstore': (0x3000, LIMIT),
}
MARKERS = (b'LYNX_', b'LOCAL_', b'Kernel panic', b'Call trace:')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_prefix(path):
    size = path.stat().st_size
    if size not in (LIMIT, 134217728):
        raise ValueError(f'Unexpected capture size: {path} ({size})')
    with path.open('rb') as stream:
        data = stream.read(LIMIT)
    if len(data) != LIMIT:
        raise ValueError('Truncated expdb capture')
    return data, size


def summarize(before, after):
    blocks = [offset for offset in range(0, LIMIT, BLOCK)
              if before[offset:offset + BLOCK] != after[offset:offset + BLOCK]]
    regions = {}
    for name, (start, end) in REGIONS.items():
        old, new = before[start:end], after[start:end]
        regions[name] = {
            'offset': start, 'bytes': end - start,
            'changed': old != new,
            'baseline_sha256': sha(old), 'candidate_sha256': sha(new),
            'changed_4k_blocks': [offset for offset in blocks if start <= offset < end],
        }
    def markers(data):
        return {key.decode(): data.count(key) for key in MARKERS}
    # Tokens are diagnostic identifiers only. Report counts, not raw log text.
    token_re = re.compile(rb'LXDG1 ([0-9a-f]{32}) ')
    token_counts = {}
    for token in token_re.findall(after):
        decoded = token.decode()
        token_counts[decoded] = token_counts.get(decoded, 0) + 1
    return {
        'prefix_bytes': LIMIT, 'equal': before == after,
        'changed_4k_blocks': blocks, 'changed_4k_block_count': len(blocks),
        'regions': regions, 'baseline_markers': markers(before),
        'candidate_markers': markers(after), 'candidate_diagnostic_tokens': token_counts,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, required=True)
    args = parser.parse_args()
    before, before_size = read_prefix(args.baseline)
    after, after_size = read_prefix(args.candidate)
    os.umask(0o077)
    out = ROOT / 'logs' / ('expdb-compare-' + str(time.time_ns()))
    out.mkdir(mode=0o700)
    result = {
        'state': 'offline-comparison-complete',
        'baseline': str(args.baseline.resolve()), 'candidate': str(args.candidate.resolve()),
        'baseline_file_bytes': before_size, 'candidate_file_bytes': after_size,
        'baseline_prefix_sha256': sha(before), 'candidate_prefix_sha256': sha(after),
        **summarize(before, after),
        'phone_contacted': False, 'partition_writes': False,
        'limits': 'Byte comparison only; unchanged data may hide compressed or proprietary records, and changed data needs provenance before attribution.',
    }
    (out / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'result': str(out / 'result.json'), 'equal': result['equal'],
                      'changed_4k_block_count': result['changed_4k_block_count'],
                      'regions': {name: item['changed'] for name, item in result['regions'].items()}}))


if __name__ == '__main__':
    main()
