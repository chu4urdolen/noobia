"""Decode authenticated-format stage records; SHA is corruption detection, not identity."""
import argparse
import hashlib
import json
import re
from pathlib import Path

PATTERN = re.compile(rb'LXDG1 ([0-9a-f]{32}) ([0-9a-f]{8}) ([0-9a-f]{8}) ([0-9a-f]{4}) ([0-9a-f]{4}) ([0-9a-f]{64})(?=\r?\n|$)')
STAGES = {1: 'PID1 entered', 2: 'reset guards passed', 16: 'base drivers',
          17: 'storage drivers', 18: 'partition discovery', 19: 'payload read',
          20: 'payload verified and extracted', 32: 'factory calibration',
          33: 'radio drivers', 34: 'chip query', 35: 'station power',
          36: 'WLAN interface', 37: 'WPA association', 38: 'DHCP',
          39: 'SSH ready', 40: 'pinned host confirmed', 240: 'fallback requested'}


def decode(data, token):
    records = []
    issues = []
    expected_sequence = 0
    for match in PATTERN.finditer(data):
        session, sequence, seconds, stage, status, digest = match.groups()
        if session.decode() != token:
            issues.append({'offset': match.start(), 'error': 'wrong session'})
            continue
        payload = match.group(0).rsplit(b' ', 1)[0]
        if hashlib.sha256(payload).hexdigest().encode() != digest:
            issues.append({'offset': match.start(), 'error': 'checksum mismatch'})
            continue
        number = int(sequence, 16)
        if number != expected_sequence:
            issues.append({'offset': match.start(), 'error': 'sequence gap or duplicate',
                           'expected': expected_sequence, 'observed': number})
        expected_sequence = number + 1
        records.append({'sequence': number, 'uptime_seconds': int(seconds, 16),
                        'stage_hex': '0x' + stage.decode(), 'stage': STAGES.get(int(stage, 16), 'unknown'),
                        'status_hex': '0x' + status.decode(), 'status': int(status, 16),
                        'offset': match.start()})
    # A damaged/truncated capsule should never disappear silently.
    starts = len(re.findall(rb'LXDG1\b', data))
    if starts != len(records) + len([i for i in issues if i['error'] != 'sequence gap or duplicate']):
        issues.append({'error': 'malformed or truncated capsule', 'capsule_starts': starts})
    return {'source_sha256': hashlib.sha256(data).hexdigest(), 'session_token': token,
            'records': records, 'issues': issues,
            'complete_sequences_and_checksums': bool(records) and not issues,
            'identity_authenticated': False,
            'limits': ['Checksums detect corruption; require pinned SSH or trusted physical retrieval for identity.',
                       'No records does not establish that Linux failed to execute.',
                       'RAM, printk and pmsg copies alone do not establish warm-reboot persistence.']}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('capture', type=Path)
    parser.add_argument('--session', required=True)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--codebook', type=Path, help='Optional codebook from the verified image manifest')
    args = parser.parse_args()
    if not re.fullmatch('[0-9a-f]{32}', args.session):
        parser.error('Expected a 32-character hexadecimal experiment session')
    report = decode(args.capture.read_bytes(), args.session)
    if args.codebook:
        codebook = json.loads(args.codebook.read_text())
        if 'diagnostic_codebook' in codebook:
            codebook = codebook['diagnostic_codebook']
        for record in report['records']:
            record['stage'] = codebook.get(str(int(record['stage_hex'], 16)), record['stage'])
    encoded = json.dumps(report, indent=2) + '\n'
    if args.output:
        args.output.write_text(encoded)
        args.output.chmod(0o600)
    print(encoded, end='')


if __name__ == '__main__':
    main()
