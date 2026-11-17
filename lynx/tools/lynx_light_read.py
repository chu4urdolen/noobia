#!/usr/bin/env python3
"""Read one bounded rear optical sample for Lynx's local tool catalog."""

import json
from pathlib import Path
import subprocess
import sys

SENSOR = 'tcs3408 als'
HELPER = '/usr/local/bin/lynx-hf-sample'


def read_request():
    raw = sys.stdin.read(4097)
    if len(raw) > 4096 or json.loads(raw) != {}:
        raise ValueError('expected an empty JSON object')


def read_light():
    if not Path('/dev/hf_manager').is_char_device() or SENSOR not in Path('/proc/hf_manager').read_text():
        raise RuntimeError('rear optical sensor unavailable')
    result = subprocess.run(['/usr/bin/python3', HELPER, '--sensor', '98',
                             '--seconds', '2', '--events', '1'],
                            capture_output=True, text=True, timeout=3)
    if result.returncode:
        raise RuntimeError('rear optical sample failed')
    sample = json.loads(result.stdout)
    info = sample.get('info', {})
    events = sample.get('events', [])
    if (sample.get('sensor_type') != 98 or not sample.get('disabled') or
            info.get('name') != SENSOR or info.get('gain') != 1 or not events):
        raise RuntimeError('rear optical sample invalid')
    raw = events[-1].get('raw_xyz')
    if (not isinstance(raw, list) or len(raw) != 3 or
            any(type(value) is not int for value in raw)):
        raise RuntimeError('rear optical fields invalid')
    return {'sensor': SENSOR, 'registered': True,
            'optical_response_verified': True, 'raw': raw, 'gain': 1,
            'unit': 'driver_raw', 'calibrated_lux': False,
            'sensor_disabled_after_sample': True}


def main():
    try:
        read_request()
        print(json.dumps(read_light(), separators=(',', ':')))
    except (OSError, ValueError, subprocess.TimeoutExpired, RuntimeError) as exc:
        print(json.dumps({'error': str(exc)}, separators=(',', ':')))
        raise SystemExit(1)


if __name__ == '__main__':
    main()
