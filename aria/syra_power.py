#!/usr/bin/env python3
"""Nexus-side graceful Syra shutdown with a cancellable five-minute Tuya cut."""
import argparse
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parent
DELAY = 300


class Power:
    def __init__(self, directory=None, config=None, clock=None, command=None, relay=None):
        self.directory = directory or ROOT / 'private'
        self.config = config or self.directory / 'smartplug.json'
        self.clock = clock or time.time
        self.command = command or self.run_command
        self.relay = relay or self.tuya
        self.state_file = self.directory / 'syra-power.json'

    @staticmethod
    def run_command(command):
        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise RuntimeError('Command failed: ' + command[0] + ' (exit ' + str(result.returncode) + ')')
        return result

    @contextmanager
    def locked(self):
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor = os.open(self.directory / 'syra-power.lock', os.O_CREAT | os.O_RDWR, 0o600)
        with os.fdopen(descriptor, 'w') as file:
            fcntl.flock(file, fcntl.LOCK_EX)
            yield

    def read(self):
        return json.loads(self.state_file.read_text()) if self.state_file.exists() else {'status': 'idle'}

    def write(self, state):
        with tempfile.NamedTemporaryFile(mode='w', dir=self.directory, delete=False) as file:
            json.dump(state, file)
            temporary = Path(file.name)
        temporary.replace(self.state_file)

    def plug_config(self):
        value = json.loads(self.config.read_text())
        if value.get('backend') != 'tuya' or value.get('powers_syra') is not True:
            raise RuntimeError('Select the protected Tuya plug that powers Syra')
        if not value.get('local_key') or not value.get('device_id'):
            raise RuntimeError('Tuya local key is missing; no SSH shutdown or relay command was sent')
        return value

    @staticmethod
    def tuya(config, action):
        from smartplug import tuya_control
        return tuya_control(config, action)

    def cancel_locked(self, reason):
        state = self.read()
        unit = state.get('unit', '')
        if state.get('status') == 'pending':
            # Invalidate the generation BEFORE stopping a timer or touching the relay.
            state.update(status='cancelled', cancelled_at=self.clock(), reason=reason)
            self.write(state)
            if re.fullmatch(r'noobia-syra-powercut-[0-9a-f]{32}', unit):
                try:
                    self.command(['systemctl', '--user', 'stop', unit + '.timer', unit + '.service'])
                except (RuntimeError, OSError, subprocess.SubprocessError):
                    pass  # Generation checks still prevent stale workers from cutting power.
        return state

    def cancel(self):
        with self.locked():
            return self.cancel_locked('explicit cancellation')

    def on(self):
        with self.locked():
            state = self.cancel_locked('turn-on request')
            result = self.relay(self.plug_config(), 'on')
            return dict(result, pending_shutdown_revoked=state.get('status') == 'cancelled')

    def shutdown(self):
        with self.locked():
            self.cancel_locked('replacement shutdown request')
            config = self.plug_config()
            # Verify credentials with a read before halting the computer.
            self.relay(config, 'status')
            self.command(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=5',
                          'rose', 'sudo -n /usr/bin/systemctl poweroff'])
            token = uuid.uuid4().hex
            unit = 'noobia-syra-powercut-' + token
            now = self.clock()
            state = dict(status='pending', generation=token, unit=unit,
                         requested_at=now, cut_at=now + DELAY)
            self.write(state)
            try:
                self.command(['systemd-run', '--user', '--collect', '--unit=' + unit,
                    '--on-active=300s', '--timer-property=AccuracySec=1s',
                    str(ROOT / '.venv/bin/python'), str(ROOT / 'syra_power.py'), '_cut', token])
            except Exception:
                state.update(status='failed', reason='Timer could not be scheduled; power remains on')
                self.write(state)
                raise
            return state

    def cut(self, token):
        with self.locked():
            state = self.read()
            if state.get('status') != 'pending' or state.get('generation') != token:
                return {'status': 'ignored', 'reason': 'revoked or stale generation'}
            if self.clock() < state['cut_at']:
                return {'status': 'ignored', 'reason': 'five-minute delay has not elapsed'}
            # A machine that has come back online must not be cut by an old plan.
            reachable = subprocess.run(['ping', '-c', '1', '-W', '2', '192.168.100.7'],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=4).returncode == 0
            if reachable:
                state.update(status='cancelled', reason='Syra is online again; automatic cut refused')
                self.write(state)
                return state
            try:
                self.relay(self.plug_config(), 'off')
                state.update(status='completed', completed_at=self.clock())
            except Exception:
                state.update(status='failed', reason='Tuya cut failed; inspect plug configuration')
                self.write(state)
                raise
            self.write(state)
            return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['on', 'shutdown', 'cancel', 'status', '_cut'],
                        help='on cancels pending cuts first; shutdown sends SSH poweroff then schedules a cut in 300 seconds')
    parser.add_argument('generation', nargs='?', help=argparse.SUPPRESS)
    parser.add_argument('--config', type=Path, default=ROOT / 'private/smartplug.json')
    parser.add_argument('--dry-run', action='store_true', help='Describe the action without SSH, timers, relay commands, or state changes')
    args = parser.parse_args()
    if args.dry_run:
        print(json.dumps({'action': args.action, 'delay_seconds': DELAY, 'executed': False,
                          'order': 'shutdown: verify relay credentials, SSH poweroff, wait 300 seconds, cut only if still valid; on: revoke pending generation, cancel timer, turn relay on'}))
        return
    if os.uname().nodename.lower() != 'nexus':
        raise RuntimeError('Run this controller on Nexus; its delayed worker must survive Syra shutdown')
    power = Power(config=args.config)
    if args.action == '_cut':
        if not args.generation:
            parser.error('Internal worker requires a generation')
        result = power.cut(args.generation)
    elif args.action == 'status':
        with power.locked():
            result = power.read()
    else:
        result = getattr(power, args.action)()
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('Syra power operation failed: ' + (str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__), file=sys.stderr)
        sys.exit(1)
