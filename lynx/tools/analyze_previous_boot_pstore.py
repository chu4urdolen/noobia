"""Summarize a previous Lynx boot from a saved, pinned pstore snapshot.

This reads a local capture only. LXDG1 hashes detect record corruption, not
device identity; the caller must supply the pinned SSH capture and both tokens.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import time

from lynx_decode_stages import decode

ROOT = Path(__file__).resolve().parent.parent
TOKEN = re.compile(r'^[0-9a-f]{32}$')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--previous-token', required=True)
    parser.add_argument('--current-token', required=True)
    args = parser.parse_args()
    if not TOKEN.fullmatch(args.previous_token) or not TOKEN.fullmatch(args.current_token):
        parser.error('Tokens must be 32 lowercase hexadecimal characters')
    if args.previous_token == args.current_token:
        parser.error('Previous and current tokens must differ')
    capture = args.capture.resolve(strict=True)
    if not capture.is_relative_to(ROOT / 'logs'):
        parser.error('Capture must be in Lynx logs')
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
        if line.startswith('LXDG1 ' + args.previous_token + ' '):
            previous_lines.append(line)
    capsule = ('\n'.join(previous_lines) + '\n').encode()
    decoded = decode(capsule, args.previous_token)
    if not decoded['complete_sequences_and_checksums']:
        raise ValueError('Previous boot stage records failed checksum/sequence validation')
    tracepoints = re.findall(
        r'^.*\blx' + args.previous_token + r'_(\d+):.*$', console, flags=re.MULTILINE)
    report = {
        'state': 'previous-boot-pstore-summarized',
        'capture': str(capture),
        'capture_sha256': hashlib.sha256(raw).hexdigest(),
        'previous_token': args.previous_token,
        'current_token': args.current_token,
        'previous_token_in_console': args.previous_token in console,
        'current_token_in_console': args.current_token in console,
        'previous_token_in_pmsg': args.previous_token in pmsg,
        'current_token_in_pmsg': args.current_token in pmsg,
        'records': decoded['records'],
        'record_checksums_and_sequence_valid': True,
        'ufs_tracepoints': [int(value) for value in tracepoints],
        'last_ufs_tracepoint': int(tracepoints[-1]) if tracepoints else None,
        'ufs_probe_returned_logged': 'UFS_CONTROLLED_PROBE_RETURNED_BOUND' in console,
        'limits': 'The saved pstore gives the last visible trace, not a proven instruction-level stop point.',
    }
    out = ROOT / 'logs' / ('pstore-previous-boot-' + str(time.time_ns()) + '.json')
    out.write_text(json.dumps(report, indent=2) + '\n')
    out.chmod(0o600)
    print(json.dumps({'state': report['state'], 'result': str(out),
                      'stages': [(r['stage_hex'], r['status']) for r in report['records']],
                      'last_ufs_tracepoint': report['last_ufs_tracepoint'],
                      'ufs_probe_returned_logged': report['ufs_probe_returned_logged']}))


if __name__ == '__main__':
    main()
