#!/usr/bin/python3
"""Physical Hue checks that verify API state and restore the original light state."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from hue_strip import request


def lock():
    path = Path('/tmp/rose-hue.lock')
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    except FileExistsError:
        try:
            owner = int(path.read_text().strip())
            os.kill(owner, 0)
        except ProcessLookupError:
            path.unlink()
            return lock()
        raise RuntimeError('Another Hue process owns the strip; stop it before testing')
    os.write(fd, f'{os.getpid()}\n'.encode())
    os.close(fd)
    return path


def restore_fields(state):
    restored = {'on': state['on'], 'transitiontime': 0}
    if 'bri' in state:
        restored['bri'] = state['bri']
    mode = state.get('colormode')
    keys = ('ct',) if mode == 'ct' else ('hue', 'sat') if mode == 'hs' else ('xy',)
    restored.update({key: state[key] for key in keys if key in state})
    # Neither test changes effect; some strips expose it but reject writes.
    return restored


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['pulse', 'voice'])
    parser.add_argument('--text', default='Hello Noob. This is Rose testing my voice and lights together.')
    args = parser.parse_args()
    config = {}
    for line in (Path(__file__).parent/'private/hue.conf').read_text().splitlines():
        if '=' in line and not line.lstrip().startswith('#'):
            key, value = line.split('=', 1)
            config[key.strip()] = value.strip()
    light_path = 'lights/1'
    light = request(config, light_path)
    if light.get('modelid') != 'LCL001' or not light['state'].get('reachable'):
        raise RuntimeError('Identified strip is missing or unreachable')
    original = light['state']
    claim = None
    player = None
    failure = None
    samples = []
    try:
        if args.mode == 'pulse':
            claim = lock()
            for _ in range(3):
                for on, duration in [(True, 1.2), (False, .6)]:
                    request(config, light_path+'/state', {'on': on, 'bri': 200, 'transitiontime': 0})
                    state = request(config, light_path)['state']
                    if state['on'] != on or (on and state['bri'] != 200):
                        raise RuntimeError('Strip did not report the requested pulse state')
                    print(f"Pulse state: {'ON' if on else 'OFF'}", flush=True)
                    time.sleep(duration)
        else:
            # Establish an off baseline, then let rose-say own the animation lock.
            claim = lock()
            request(config, light_path+'/state', {'on': False, 'transitiontime': 0})
            claim.unlink(); claim = None
            player = subprocess.Popen([str(Path.home()/'.local/bin/rose-say'), args.text],
                                      env={**os.environ, 'ROSE_HUE_ENABLED': '1'}, start_new_session=True)
            deadline = time.monotonic()+120
            while player.poll() is None:
                if time.monotonic() > deadline:
                    raise RuntimeError('Speech test exceeded 120 seconds')
                state = request(config, light_path)['state']
                samples.append({'on': state['on'], 'brightness': state.get('bri')})
                time.sleep(.15)
            if player.returncode:
                raise RuntimeError('Speech command failed')
            lit = [s['brightness'] for s in samples if s['on']]
            print(json.dumps({'samples': len(samples), 'lit_samples': len(lit),
                              'distinct_lit_brightness': sorted(set(lit))}), flush=True)
            if not lit:
                raise RuntimeError('Speech played but the strip never reported ON')
            if len(set(lit)) < 2:
                raise RuntimeError('Strip turned on but no speech brightness modulation was observed')
        print('PASS: direct pulse states' if args.mode == 'pulse' else 'PASS: speech playback and observed light modulation', flush=True)
    except BaseException as exc:
        failure = exc
    finally:
        if player and player.poll() is None:
            try:
                os.killpg(player.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                player.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(player.pid, signal.SIGKILL)
                player.wait()
        if claim is None:
            claim = lock()
        try:
            request(config, light_path+'/state', restore_fields(original))
            state = request(config, light_path)['state']
            if state['on'] != original['on'] or state.get('bri') != original.get('bri'):
                raise RuntimeError('Original strip state did not restore')
            print('Original strip state restored.', flush=True)
        finally:
            claim.unlink()
    if failure:
        raise failure


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as exc:
        # HTTP exceptions contain credential-bearing URLs. Report safe diagnostics only.
        print(f'Test failed: {exc if isinstance(exc, RuntimeError) else type(exc).__name__}', file=sys.stderr)
        sys.exit(1)
