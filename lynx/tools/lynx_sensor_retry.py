#!/usr/bin/env python3
"""Retry optional audio and sensorhub startup after Lynx charges enough.

This never changes charging, shuts down, reboots, or loads modules directly.
The existing guarded OpenRC services retain control of hardware bring-up.
"""

import argparse
import json
from pathlib import Path
import subprocess
import time

from lynx_sensor_retry_policy import ATTEMPT_START, ALREADY_READY, classify_retry_policy

SNAPSHOT = Path('/sys/bus/i2c/devices/7-0055/battery_snapshot')
SOC = Path('/sys/class/thermal/thermal_zone0')
INTERVAL_S = 60
FAILED_RETRY_S = 300
MAX_FAILED_ATTEMPTS = 3
REQUIRED = ('gauge_device_type', 'capacity_percent',
            'temperature_millidegrees_celsius', 'gauge_current_ma_signed',
            'capacity_error', 'temperature_error', 'current_error')


def command(*args, timeout=8):
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout,
                          check=False)


def service_ready(name):
    return command('/sbin/rc-service', name, 'status').returncode == 0


def interfaces():
    audio = service_ready('lynx-audio') and Path('/proc/asound/cards').is_file() and \
        'mt6983mt6338' in Path('/proc/asound/cards').read_text()
    sensor = service_ready('lynx-sensorhub') and Path('/dev/hf_manager').is_char_device() and \
        Path('/proc/hf_manager').is_file() and \
        'bmi2xy acc' in Path('/proc/hf_manager').read_text()
    return audio, sensor


def snapshot():
    values = {}
    raw = SNAPSHOT.read_text()
    if len(raw) > 4096:
        raise ValueError('gauge snapshot too large')
    for line in raw.splitlines():
        if '=' not in line:
            continue
        key, value = line.split('=', 1)
        if key in values:
            raise ValueError('duplicate gauge field')
        if key in REQUIRED or key.endswith('_error'):
            values[key] = int(value)
    return values


def probe():
    try:
        audio, sensor = interfaces()
        if SOC.joinpath('type').read_text().strip() != 'soc_max':
            raise ValueError('thermal zone 0 is not soc_max')
        soc_temp = int(SOC.joinpath('temp').read_text().strip())
        state = command('/usr/local/bin/lynx-status', '--assert-ready', timeout=10)
        healthy = state.returncode == 0 and not json.loads(state.stdout).get('issues')
        decision = classify_retry_policy(snapshot(), soc_temp, healthy, audio, sensor)
        return {'action': decision.action, 'reason': decision.reason,
                'audio_ready': audio, 'sensorhub_ready': sensor}
    except (OSError, ValueError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        return {'action': 'wait', 'reason': 'probe failed: ' + str(exc)[:120],
                'audio_ready': False, 'sensorhub_ready': False}


def event(kind, **fields):
    print(json.dumps({'event': kind, **fields}, sort_keys=True), flush=True)


def idle_until_stopped():
    """Keep OpenRC's supervised process alive after the one-time retry."""
    while True:
        time.sleep(3600)


def watch():
    failed = 0
    previous = None
    while True:
        state = probe()
        marker = (state['action'], state['reason'])
        if marker != previous:
            event('decision', **state)
            previous = marker
        if state['action'] == ALREADY_READY:
            idle_until_stopped()
            return 0
        if state['action'] == ATTEMPT_START:
            try:
                if not state['audio_ready']:
                    result = command('/sbin/rc-service', 'lynx-audio', 'start', timeout=90)
                    if result.returncode:
                        raise RuntimeError('audio service refused startup')
                if not state['sensorhub_ready']:
                    result = command('/sbin/rc-service', 'lynx-sensorhub', 'start', timeout=45)
                    if result.returncode:
                        raise RuntimeError('sensorhub service refused startup')
                audio, sensor = interfaces()
                if not (audio and sensor):
                    raise RuntimeError('service interfaces absent after startup')
                event('ready', audio_ready=True, sensorhub_ready=True)
                idle_until_stopped()
                return 0
            except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
                failed += 1
                event('start_failed', attempt=failed, reason=str(exc)[:120])
                if failed >= MAX_FAILED_ATTEMPTS:
                    return 1
                time.sleep(FAILED_RETRY_S)
                continue
        time.sleep(INTERVAL_S)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--probe', action='store_true')
    mode.add_argument('--watch', action='store_true')
    args = parser.parse_args()
    if args.probe:
        print(json.dumps(probe(), sort_keys=True))
        return 0
    return watch()


if __name__ == '__main__':
    raise SystemExit(main())
