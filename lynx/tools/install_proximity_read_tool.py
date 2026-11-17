#!/usr/bin/env python3
"""Install Lynx's local proximity reader without a reboot or daemon restart."""

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
    (TOOLS / 'lynx_proximity_read.py', '/usr/local/bin/lynx-proximity-read', '755'),
    (TOOLS / 'local_calls/lynx_proximity_read.sh',
     '/usr/local/share/lynx/agent-tools/lynx_proximity_read.sh', '755'),
    (TOOLS / 'local_calls/lynx_proximity_read.json',
     '/usr/local/share/lynx/agent-tools/lynx_proximity_read.json', '644'),
)

sys.path.insert(0, str(TOOLS))
from lynx_wifi_v19_contact import ssh_command  # noqa: E402


def remote(command, data=None):
    argv = ssh_command(HOST, command)
    argv[-2:-2] = ['-p', '2222']
    result = subprocess.run(argv, input=data, capture_output=True, timeout=25)
    if result.returncode:
        raise RuntimeError('Lynx SSH command failed: ' +
                           result.stderr.decode(errors='replace')[-300:])
    return result.stdout.decode(errors='replace')


def main():
    state = json.loads(remote('/usr/local/bin/lynx-status --assert-ready'))
    if state.get('issues') or state['battery']['capacity_percent'] < 20:
        raise RuntimeError('Lynx health gate failed')
    if remote('test -c /dev/hf_manager && grep -q "tcs3701 ps" /proc/hf_manager && echo ready').strip() != 'ready':
        raise RuntimeError('proximity interface absent')
    targets = [target for _, target, _ in FILES]
    for target in targets:
        remote(f'test ! -e {target}')
    installed = []
    try:
        for source, target, mode in FILES:
            payload = source.read_bytes()
            digest = remote(f'cat > {target} && chmod {mode} {target} && sha256sum {target}', payload).split()[0]
            installed.append(target)
            if digest != hashlib.sha256(payload).hexdigest():
                raise RuntimeError('upload hash mismatch: ' + target)
        call = remote("printf '{}' | /usr/local/share/lynx/agent-tools/lynx_proximity_read.sh")
        observed = json.loads(call)
        if (observed.get('sensor') != 'tcs3701 ps' or
                observed.get('sensor_disabled_after_sample') is not True or
                len(observed.get('raw', [])) != 3):
            raise RuntimeError('local proximity call returned invalid data')
        health = json.loads(remote('/usr/local/bin/lynx-status --assert-ready'))
        if health.get('issues') or health['boot_id'] != state['boot_id']:
            raise RuntimeError('post-install health or boot identity changed')
    except Exception:
        if installed:
            remote('rm -f ' + ' '.join(installed))
        raise
    receipt = {'state': 'installed', 'boot_id': state['boot_id'],
               'files': targets, 'sample': observed,
               'boot_partition_writes': False, 'service_restart': False}
    out = ROOT / 'lynx/logs' / f'proximity-local-tool-{time.time_ns()}'
    out.mkdir(parents=True, mode=0o700)
    (out / 'result.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps({'state': 'installed', 'receipt': str(out / 'result.json'),
                      'sample': observed}))


if __name__ == '__main__':
    main()
