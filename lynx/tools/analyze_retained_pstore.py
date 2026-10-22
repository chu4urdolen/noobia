"""Summarize a retained Lynx pstore token and check candidate provenance.

This reads local files only. A pstore token can be older than the immediately
preceding boot; matching a candidate token is necessary but not sufficient
for attribution because several Lynx images reuse one static token.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import time

from lynx_decode_stages import decode
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'linux-port'))
from image_formats import read_boot_v4, read_newc
from ramdisk_codec import decompress

ROOT = Path(__file__).resolve().parent.parent
TOKEN = re.compile(r'^[0-9a-f]{32}$')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--retained-token', required=True)
    parser.add_argument('--candidate-image', type=Path, required=True)
    args = parser.parse_args()
    if not TOKEN.fullmatch(args.retained_token):
        parser.error('Retained token must be 32 lowercase hexadecimal characters')
    capture = args.capture.resolve(strict=True)
    image = args.candidate_image.resolve(strict=True)
    if not capture.is_relative_to(ROOT / 'logs') or not image.is_relative_to(ROOT / 'linux-port/artifacts'):
        parser.error('Capture and image must be in Lynx logs/artifacts')
    image_data = image.read_bytes()
    primary = read_newc(decompress(read_boot_v4(image_data)['ramdisk']))
    candidate_token = primary['etc/lynx/session-token']['data'].decode().strip()
    if not TOKEN.fullmatch(candidate_token):
        raise ValueError('Candidate image token malformed')
    raw = capture.read_bytes()
    text = raw.decode(errors='replace')
    console = text.split('FILE /sys/fs/pstore/console-ramoops-0\n', 1)
    if len(console) != 2:
        raise ValueError('No saved console-ramoops section')
    console = console[1].split('\nFILE /sys/fs/pstore/', 1)[0]
    pmsg = text.split('FILE /sys/fs/pstore/pmsg-ramoops-0\n', 1)
    if len(pmsg) != 2:
        raise ValueError('No saved pmsg-ramoops section')
    pmsg = pmsg[1].split('\nBOOT_LOG\n', 1)[0]
    previous_lines = []
    for line in pmsg.splitlines():
        if line.startswith('LXDG1 ' + args.retained_token + ' '):
            previous_lines.append(line)
    capsule = ('\n'.join(previous_lines) + '\n').encode()
    decoded = decode(capsule, args.retained_token)
    if not decoded['complete_sequences_and_checksums']:
        raise ValueError('Retained stage records failed checksum/sequence validation')
    tracepoints = re.findall(
        r'^.*\blx' + args.retained_token + r'_(\d+):.*$', console, flags=re.MULTILINE)
    matches_candidate = args.retained_token == candidate_token
    report = {
        'state': 'retained-pstore-token-summarized',
        'capture': str(capture),
        'capture_sha256': hashlib.sha256(raw).hexdigest(),
        'candidate_image': str(image),
        'candidate_image_sha256': hashlib.sha256(image_data).hexdigest(),
        'retained_token': args.retained_token,
        'candidate_token': candidate_token,
        'retained_token_matches_candidate': matches_candidate,
        'candidate_attribution_proven': False,
        'retained_token_in_console': args.retained_token in console,
        'candidate_token_in_console': candidate_token in console,
        'retained_token_in_pmsg': args.retained_token in pmsg,
        'candidate_token_in_pmsg': candidate_token in pmsg,
        'records': decoded['records'],
        'record_checksums_and_sequence_valid': True,
        'ufs_tracepoints': [int(value) for value in tracepoints],
        'last_ufs_tracepoint': int(tracepoints[-1]) if tracepoints else None,
        'ufs_probe_returned_logged': 'UFS_CONTROLLED_PROBE_RETURNED_BOUND' in console,
        'limits': ('A different token excludes this candidate. A matching static token alone cannot '
                   'identify the immediately preceding boot or an instruction-level stop point.'),
    }
    out = ROOT / 'logs' / ('pstore-retained-token-' + str(time.time_ns()) + '.json')
    out.write_text(json.dumps(report, indent=2) + '\n')
    out.chmod(0o600)
    print(json.dumps({'state': report['state'], 'result': str(out),
                      'stages': [(r['stage_hex'], r['status']) for r in report['records']],
                      'retained_token_matches_candidate': matches_candidate,
                      'last_ufs_tracepoint': report['last_ufs_tracepoint'],
                      'ufs_probe_returned_logged': report['ufs_probe_returned_logged']}))


if __name__ == '__main__':
    main()
