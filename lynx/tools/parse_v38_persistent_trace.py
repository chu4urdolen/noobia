"""Verify and summarize V38's small checksummed per-boot ext4 stage logs."""
import argparse
import hashlib
import json
from pathlib import Path
import re

BOOT_ID = re.compile(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}')
LINE = re.compile(r'(LXBD1) (' + BOOT_ID.pattern +
                  r') ([0-9]+) (START|WIFI_READY|WIFI_FAILED|WIFI_NO_RESULT|'
                  r'WIFI_ERR_[0-9]{1,3}|UPTIME_120|'
                  r'UPTIME_150|UPTIME_180|HEALTH_BEGIN|HEALTH_FAILED|'
                  r'HEALTH_FAIL_PRECHECK|HEALTH_FAIL_CHILD|HEALTH_FAIL_WATCHER|'
                  r'HEALTH_FAIL_BATTERY|HEALTH_FAIL_THERMAL|'
                  r'HEALTH_FAIL_POSTCHECK|HEALTH_FAIL_LOG|'
                  r'HEALTH_READY|HANDOFF_BEGIN|TIMER_CANCELLED|HANDOFF_REFUSED|'
                  r'CHARGER_ON|END) ([0-9a-f]{64})')


def parse(path):
    path = path.resolve(strict=True)
    if not BOOT_ID.fullmatch(path.stem) or path.suffix != '.log':
        raise ValueError('Log filename is not a boot ID: ' + str(path))
    raw = path.read_bytes()
    if not 1 <= len(raw) <= 4096 or not raw.endswith(b'\n'):
        raise ValueError('Log size or final newline differs: ' + str(path))
    try:
        lines = raw.decode('ascii').splitlines()
    except UnicodeDecodeError as error:
        raise ValueError('Log is not ASCII: ' + str(path)) from error
    events = []
    for number, line in enumerate(lines, 1):
        match = LINE.fullmatch(line)
        if not match or match.group(2) != path.stem:
            raise ValueError(f'Invalid V38 record at line {number}: {path}')
        payload = ' '.join(match.groups()[:-1]) + '\n'
        if hashlib.sha256(payload.encode('ascii')).hexdigest() != match.group(5):
            raise ValueError(f'Checksum mismatch at line {number}: {path}')
        uptime = int(match.group(3))
        if events and uptime < events[-1]['uptime_seconds']:
            raise ValueError(f'Uptime reversed at line {number}: {path}')
        events.append({'uptime_seconds': uptime, 'stage': match.group(4)})
    if events[0]['stage'] != 'START':
        raise ValueError('First V38 record is not START: ' + str(path))
    return {'boot_id': path.stem, 'source': str(path),
            'source_sha256': hashlib.sha256(raw).hexdigest(),
            'bytes': len(raw), 'events': events,
            'last_stage': events[-1]['stage'],
            'terminal_marker_seen': events[-1]['stage'].startswith('WIFI_ERR_') or events[-1]['stage'] in
            ('END', 'HANDOFF_REFUSED', 'CHARGER_ON', 'WIFI_FAILED', 'HEALTH_FAILED',
             'WIFI_NO_RESULT',
             'HEALTH_FAIL_PRECHECK', 'HEALTH_FAIL_CHILD',
             'HEALTH_FAIL_WATCHER', 'HEALTH_FAIL_BATTERY',
             'HEALTH_FAIL_THERMAL', 'HEALTH_FAIL_POSTCHECK',
             'HEALTH_FAIL_LOG')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('logs', nargs='+', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    report = {'state': 'v38-persistent-records-verified',
              'logs': [parse(path) for path in args.logs]}
    data = json.dumps(report, indent=2) + '\n'
    if args.output:
        args.output.write_text(data)
    print(data, end='')


if __name__ == '__main__':
    main()
