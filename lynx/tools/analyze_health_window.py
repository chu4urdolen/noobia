"""Summarize preserved Lynx health-window samples without contacting the phone."""
import argparse
import hashlib
import json
from pathlib import Path
import re


BOOT_ID = re.compile(r"^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$")
UPTIME = re.compile(r"^\d+(?:\.\d+)?(?:\s+\d+(?:\.\d+)?)?$")
MARKERS = (
    'LOCAL_WIFI_SSH_READY', 'LOCAL_HEALTH_BOOT_CHILD_BEGIN',
    'COOLING_TEMPERATURE_WAIT', 'COOLING_WATCH_CLEAN_RETRY',
    'THERMAL_COOLING_READY', 'THERMAL_COOLING_SAMPLE',
    'READY_ON_PHONE_MONITORING_ACTIVE', 'LOCAL_HEALTH_BOOT_READY',
    'LOCAL_WIFI_AND_HEALTH_READY', 'PERSISTENT_OPENRC_PID1_HANDOFF_BEGIN',
    'LOCAL_HEALTH_FAILED', 'POWER_OFF_REQUESTED',
)


def parse(raw):
    lines = raw.decode('utf-8', errors='replace').splitlines()
    result = {'complete': 'END_SAMPLE' in lines, 'boot_id': None,
              'uptime_seconds': None, 'pid1_exe': None, 'markers': [],
              'has_kernel_tail': 'KERNEL_TAIL' in lines,
              'has_process_table': 'PROCESS_TABLE' in lines}
    if 'SAMPLE_BEGIN' not in lines:
        return result
    start = lines.index('SAMPLE_BEGIN')
    header = lines[start + 1:start + 5]
    for line in header:
        if BOOT_ID.fullmatch(line):
            result['boot_id'] = line
        elif UPTIME.fullmatch(line) and ' ' in line:
            result['uptime_seconds'] = float(line.split()[0])
    for line in lines:
        if line.startswith('PID1_EXE='):
            result['pid1_exe'] = line.partition('=')[2]
        if any(marker in line for marker in MARKERS):
            # Keep only the diagnostic event, never an entire process command.
            if line.startswith(('LYNX_WIFI ', 'LYNX_HEALTH_BOOT ',
                                'THERMAL_COOLING_', 'LOCAL_',
                                'LYNX_HEALTH_')):
                result['markers'].append(line[:240])
    result['markers'] = list(dict.fromkeys(result['markers']))
    return result


def analyze(receipt):
    data = json.loads(receipt.read_text())
    samples = []
    for index, item in enumerate(data.get('samples', []), 1):
        path = receipt.parent / f'sample-{index}.raw'
        raw = path.read_bytes()
        actual = hashlib.sha256(raw).hexdigest()
        if item.get('sha256') and item['sha256'] != actual:
            raise ValueError(f'Raw sample hash differs: {path}')
        sample = parse(raw)
        sample.update(index=index, started_ns=item.get('started_ns'),
                      finished_ns=item.get('finished_ns'),
                      exit_code=item.get('exit_code'),
                      timed_out=item.get('timed_out', False),
                      bytes=len(raw), sha256=actual)
        samples.append(sample)
    boots = {}
    for sample in samples:
        if sample['boot_id']:
            boot = boots.setdefault(sample['boot_id'], {'samples': 0,
                                                        'first_uptime_seconds': None,
                                                        'last_uptime_seconds': None,
                                                        'markers': []})
            boot['samples'] += 1
            if boot['first_uptime_seconds'] is None:
                boot['first_uptime_seconds'] = sample['uptime_seconds']
            boot['last_uptime_seconds'] = sample['uptime_seconds']
            boot['markers'] = list(dict.fromkeys(boot['markers'] + sample['markers']))
    return {'source': str(receipt.resolve()), 'source_sha256':
            hashlib.sha256(receipt.read_bytes()).hexdigest(),
            'samples': samples, 'boots': boots, 'phone_contacted': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('receipt', type=Path)
    parser.add_argument('--output', type=Path, help='write a new JSON file; refuse overwrite')
    args = parser.parse_args()
    report = analyze(args.receipt)
    encoded = json.dumps(report, indent=2) + '\n'
    if args.output:
        with args.output.open('x') as stream:
            stream.write(encoded)
        print(args.output)
    else:
        print(encoded, end='')


if __name__ == '__main__':
    main()
