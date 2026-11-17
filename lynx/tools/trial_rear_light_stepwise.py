#!/usr/bin/env python3
"""Record three cued, read-only rear light sensor phases on Lynx."""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import time

ROOT = Path(__file__).resolve().parent.parent
LOGS = ROOT / 'logs'
CLIENT = Path(__file__).with_name('lynx_noobctl.py')
PHASES = ('lit', 'covered', 'relit')
REPLY = re.compile(r'NRP/1 1 OK value=(\d+) detail=raw1=(\d+) raw2=(\d+) gain=(\d+)\Z')


def call(*words):
    result = subprocess.run(['python3', str(CLIENT), *words],
                            capture_output=True, text=True, timeout=12)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or 'Lynx NRP call failed')
    return result.stdout.strip()


def session_path(value, phase):
    if phase == 'lit':
        if value:
            raise ValueError('lit phase creates a new session')
        path = LOGS / ('rear-light-stepwise-' + str(time.time_ns()))
        path.mkdir(mode=0o700)
        return path
    if not value:
        raise ValueError('covered and relit need --session')
    path = Path(value)
    if path.parent != LOGS or not re.fullmatch(r'rear-light-stepwise-\d+', path.name):
        raise ValueError('invalid session path')
    if path.is_symlink() or not path.is_dir():
        raise ValueError('session directory missing or redirected')
    expected = 'lit' if phase == 'covered' else 'covered'
    if not (path / (expected + '.json')).is_file():
        raise ValueError('previous phase missing')
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=PHASES)
    parser.add_argument('--session')
    args = parser.parse_args()
    os.umask(0o077)
    session = session_path(args.session, args.phase)
    target = session / (args.phase + '.json')
    if target.exists() or target.is_symlink():
        raise SystemExit('phase already recorded')
    if 'value=1 detail=registered=1' not in call('CALL', 'LIGHT_STATUS'):
        raise SystemExit('rear light sensor is not registered')
    samples = []
    for index in range(5):
        response = call('CALL', 'LIGHT_RAW')
        match = REPLY.fullmatch(response)
        if not match:
            raise RuntimeError('unexpected light sensor response')
        value, raw1, raw2, gain = map(int, match.groups())
        samples.append({'time_ns': time.time_ns(), 'value': value,
                        'raw1': raw1, 'raw2': raw2, 'gain': gain})
        if index < 4:
            time.sleep(0.3)
    report = {'phase': args.phase, 'session': str(session), 'samples': samples,
              'read_only': True, 'boot_partition_writes': False}
    target.write_text(json.dumps(report, indent=2) + '\n')
    values = [sample['value'] for sample in samples]
    print(json.dumps({'phase': args.phase, 'session': str(session),
                      'values': values, 'median': sorted(values)[2]}))


if __name__ == '__main__':
    main()
