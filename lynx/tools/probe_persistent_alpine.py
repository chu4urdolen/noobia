"""Run Lynx's read-only persistent Alpine probe over pinned native SSH."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from lynx_wifi_v19_contact import PROOF, proof_valid, ssh_command


ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / 'linux-port/persistent-alpine-probe.sh'
IP = '192.168.100.4'
V19_SHA = '5ce2dbf8a7c132fa7e31f6be70aa76f83afe8c293e2cd5f02251a532486fd851'


def main():
    os.umask(0o077)
    script = SCRIPT.read_bytes()
    if not script.startswith(b'#!/bin/sh\n') or len(script) > 16_384:
        raise ValueError('Probe source differs from reviewed shape')
    out = ROOT / 'logs' / ('persistent-alpine-probe-' + str(time.time_ns()))
    out.mkdir(mode=0o700)
    report = {'state': 'starting', 'created_ns': time.time_ns(),
              'phone_ip': IP, 'script_sha256': hashlib.sha256(script).hexdigest(),
              'phone_partition_writes': False, 'boot_image_changed': False}

    def save():
        path = out / 'result.tmp'
        path.write_text(json.dumps(report, indent=2) + '\n')
        path.replace(out / 'result.json')

    save()
    try:
        identity = subprocess.run(ssh_command(IP, PROOF), capture_output=True,
                                  timeout=15)
        if not proof_valid(identity.stdout.decode(errors='replace'), identity.returncode):
            raise ValueError('Pinned native V19 SSH identity refused')
        preflight = '''set -eu
cat /proc/sys/kernel/random/boot_id
/bin/busybox sha256sum /dev/sdc39
cat /run/lynx/health-bootstrap/ready
! grep -F ' /run/lynx/persistent-alpine-probe ' /proc/mounts'''
        before = subprocess.run(ssh_command(IP, preflight), capture_output=True,
                                timeout=30)
        (out / 'preflight.stdout').write_bytes(before.stdout)
        (out / 'preflight.stderr').write_bytes(before.stderr)
        lines = before.stdout.decode(errors='replace').splitlines()
        if (before.returncode or len(lines) != 3 or
                lines[1] != V19_SHA + '  /dev/sdc39' or lines[2] != 'ready'):
            raise ValueError('Live preflight refused')
        boot_id = lines[0]
        report.update(state='live-preflight-passed', boot_id=boot_id)
        save()
        with SCRIPT.open('rb') as source:
            trial = subprocess.run(ssh_command(IP, 'sh -s -- ' + boot_id),
                                   stdin=source, capture_output=True, timeout=30)
        (out / 'probe.stdout').write_bytes(trial.stdout)
        (out / 'probe.stderr').write_bytes(trial.stderr)
        report['probe_exit_code'] = trial.returncode
        if (trial.returncode or
                b'PERSISTENT_ALPINE_PROBE_PASSED\n' not in trial.stdout):
            raise ValueError('Live Alpine probe failed; inspect raw output')
        after = subprocess.run(ssh_command(IP, '''set -eu
! grep -F ' /run/lynx/persistent-alpine-probe ' /proc/mounts
! grep -Eq '^/dev/sdc85 |^/dev/block/by-name/userdata ' /proc/mounts
cat /proc/sys/kernel/random/boot_id
cat /run/lynx/health-bootstrap/ready'''), capture_output=True, timeout=15)
        (out / 'postflight.stdout').write_bytes(after.stdout)
        (out / 'postflight.stderr').write_bytes(after.stderr)
        if after.returncode or after.stdout.decode(errors='replace').splitlines() != [boot_id, 'ready']:
            raise ValueError('Post-probe mount or health check failed')
        report['state'] = 'persistent-alpine-read-only-probe-passed'
    except Exception as error:
        report.update(state='failed-or-incomplete', error=str(error))
    report['finished_ns'] = time.time_ns()
    save()
    print(json.dumps({'state': report['state'], 'result': str(out / 'result.json')}))
    if report['state'] != 'persistent-alpine-read-only-probe-passed':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
