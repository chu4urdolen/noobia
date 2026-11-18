#!/usr/bin/env python3
"""Bounded local agent reader for one Lynx accel or gyro motion sample.

The agent sends a bounded JSON request on standard input: exactly
``{"choice": "accel"}`` or ``{"choice": "gyro"}`` (at most 4096 bytes;
empty or malformed requests are rejected).  The reader verifies the
``/dev/hf_manager`` character device and the ``/proc/hf_manager``
registration, then invokes ``/usr/local/bin/lynx-hf-sample`` for one
second with at most 3 events (3 second timeout), requires the sensor to
be reported disabled after sampling, matches the exact sensor info, and
returns the last uncalibrated raw sample (3 integer axes) as concise
JSON.  No calibrated values, no network, no service changes.
"""

import json
import subprocess
import sys
from pathlib import Path

MAX_INPUT = 4096
SECONDS = "1"
MAX_EVENTS = 3
TIMEOUT = 3
DEV_PATH = Path('/dev/hf_manager')
PROC_PATH = Path('/proc/hf_manager')
HELPER = '/usr/local/bin/lynx-hf-sample'

# hf_manager sensor identities and raw ranges for the two choices.
SENSORS = {
    'accel': {'sensor_type': 1, 'name': 'bmi2xy acc',
              'gain': 1000, 'raw_limit': 100000},
    'gyro': {'sensor_type': 4, 'name': 'bmi2xy gyro',
             'gain': 1000000, 'raw_limit': 1000000},
}


def read_request(text):
    """Validate bounded empty-or-choice JSON input and return the choice."""
    if len(text) > MAX_INPUT:
        raise ValueError('input exceeds the %d byte bound' % MAX_INPUT)
    if text.strip() == '':
        raise ValueError('expected a JSON choice request')
    try:
        doc = json.loads(text)
    except json.JSONDecodeError:
        raise ValueError('expected bounded JSON choice request')
    if not isinstance(doc, dict) or set(doc) != {'choice'}:
        raise ValueError('expected exactly one choice key')
    choice = doc['choice']
    if not isinstance(choice, str) or choice not in SENSORS:
        raise ValueError('choice must be accel or gyro')
    return choice


def device_ok(dev, proc, spec):
    """Require the char device and the sensor registration in procfs."""
    if not dev.is_char_device():
        return False
    try:
        return spec['name'] in proc.read_text()
    except OSError:
        return False


def take_sample(spec, runner=subprocess.run):
    """Run one bounded lynx-hf-sample round and parse its JSON output."""
    result = runner(['/usr/bin/python3', HELPER,
                     '--sensor', str(spec['sensor_type']),
                     '--seconds', SECONDS, '--events', str(MAX_EVENTS)],
                    capture_output=True, text=True, timeout=TIMEOUT)
    if result.returncode:
        raise RuntimeError('motion sample failed')
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        raise RuntimeError('motion sample output invalid')


def validate_sample(sample, spec):
    """Enforce disabled state, exact sensor info, and 3 integer axes."""
    if not isinstance(sample, dict) or sample.get('sensor_type') != spec['sensor_type']:
        raise RuntimeError('motion sensor type mismatch')
    if sample.get('disabled') is not True:
        raise RuntimeError('motion sensor not disabled after sample')
    info = sample.get('info')
    if (not isinstance(info, dict) or info.get('name') != spec['name'] or
            info.get('gain') != spec['gain']):
        raise RuntimeError('motion sensor info mismatch')
    events = sample.get('events')
    if not isinstance(events, list) or not 1 <= len(events) <= MAX_EVENTS:
        raise RuntimeError('motion event count invalid')
    last = events[-1]
    if not isinstance(last, dict):
        raise RuntimeError('motion event invalid')
    raw = last.get('raw_xyz')
    if (not isinstance(raw, list) or len(raw) != 3 or
            any(type(value) is not int for value in raw)):
        raise RuntimeError('motion raw axes invalid')
    if any(abs(value) > spec['raw_limit'] for value in raw):
        raise RuntimeError('motion raw value out of range')
    return raw


def read_motion(choice, runner=subprocess.run, dev=DEV_PATH, proc=PROC_PATH):
    """Read one bounded, disabled, uncalibrated sample for the choice."""
    spec = SENSORS[choice]
    if not device_ok(dev, proc, spec):
        raise RuntimeError('hf_manager motion sensor unavailable')
    raw = validate_sample(take_sample(spec, runner), spec)
    return {'choice': choice, 'sensor': spec['name'], 'registered': True,
            'raw': raw, 'gain': spec['gain'], 'unit': 'driver_raw',
            'calibrated': False, 'sensor_disabled_after_sample': True}


def main():
    try:
        choice = read_request(sys.stdin.read(MAX_INPUT + 1))
        print(json.dumps(read_motion(choice), separators=(',', ':')))
    except (OSError, ValueError, subprocess.TimeoutExpired, RuntimeError) as exc:
        print(json.dumps({'error': str(exc)}, separators=(',', ':')))
        raise SystemExit(1)


if __name__ == '__main__':
    main()
