#!/usr/bin/env python3
"""Install Lynx's optional audio/sensorhub retry without reboot or flash."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / 'lynx/tools'
HOST = '192.168.100.107'
FILES = (
    (TOOLS / 'lynx_sensor_retry_policy.py', '/usr/local/bin/lynx_sensor_retry_policy.py', '644'),
    (TOOLS / 'lynx_sensor_retry.py', '/usr/local/bin/lynx-sensor-retry', '755'),
    (TOOLS / 'lynx-sensor-retry.openrc.sh', '/etc/init.d/lynx-sensor-retry', '755'),
)

sys.path.insert(0, str(TOOLS))
from lynx_wifi_v19_contact import ssh_command  # noqa: E402


def remote(command, data=None):
    argv = ssh_command(HOST, command)
    argv[-2:-2] = ['-p', '2222']
    result = subprocess.run(argv, input=data, capture_output=True, timeout=30)
    if result.returncode:
        raise RuntimeError('Lynx SSH command failed: ' +
                           result.stderr.decode(errors='replace')[-300:])
    return result.stdout.decode(errors='replace')


def main():
    state = json.loads(remote('/usr/local/bin/lynx-status --assert-ready'))
    if state.get('issues') or state['battery']['capacity_percent'] < 50 or \
            state['battery']['temperature_mC'] >= 35000:
        raise RuntimeError('Lynx health or installation charge gate failed')
    if remote('rc-service lynx-audio status >/dev/null && '
              'rc-service lynx-sensorhub status >/dev/null && echo ready').strip() != 'ready':
        raise RuntimeError('audio/sensorhub must already be healthy for installation')
    for _, target, _ in FILES:
        remote(f'test ! -e {target} && test ! -e {target}.incoming')

    installed = []
    enabled = False
    try:
        for source, target, mode in FILES:
            payload = source.read_bytes()
            candidate = target + '.incoming'
            digest = remote(f'cat > {candidate} && chmod {mode} {candidate} && '
                            f'sha256sum {candidate}', payload).split()[0]
            if digest != hashlib.sha256(payload).hexdigest():
                raise RuntimeError('upload hash mismatch: ' + target)
            remote(f'mv {candidate} {target} && test -f {target}')
            installed.append(target)
        probe = json.loads(remote('/usr/bin/python3 /usr/local/bin/lynx-sensor-retry --probe'))
        if probe.get('action') != 'already_ready' or not probe.get('sensorhub_ready'):
            raise RuntimeError('live read-only retry probe did not see ready services')
        remote('rc-update add lynx-sensor-retry default')
        enabled = True
        remote('rc-service lynx-sensor-retry start')
        remote('test -L /etc/runlevels/default/lynx-sensor-retry')
        health = json.loads(remote('/usr/local/bin/lynx-status --assert-ready'))
        if health.get('issues') or health['boot_id'] != state['boot_id']:
            raise RuntimeError('post-install health or boot identity changed')
    except Exception:
        if enabled:
            try:
                remote('rc-service lynx-sensor-retry stop >/dev/null 2>&1 || true; '
                       'rc-update del lynx-sensor-retry default >/dev/null 2>&1 || true')
            except RuntimeError:
                pass
        if installed:
            try:
                remote('rm -f ' + ' '.join(installed))
            except RuntimeError:
                pass
        raise
    receipt = {'state': 'installed', 'boot_id': state['boot_id'],
               'files': [target for _, target, _ in FILES],
               'probe': probe, 'default_runlevel': True,
               'boot_partition_writes': False, 'reboot': False,
               'cold_boot_retry_verified': False}
    out = ROOT / 'lynx/logs' / f'sensor-retry-install-{time.time_ns()}'
    out.mkdir(parents=True, mode=0o700)
    (out / 'result.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps({'state': 'installed', 'receipt': str(out / 'result.json'),
                      'probe': probe}))


if __name__ == '__main__':
    main()
