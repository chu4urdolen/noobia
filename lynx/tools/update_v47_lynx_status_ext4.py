"""Add read-only ext4 error reporting to the installed Lynx status tool."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from lynx_wifi_v19_contact import ssh_command


ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / 'linux-port/lynx-status.py'
IP = '192.168.100.8'
BOOT_ID = '9054078d-aafa-4abf-9600-5c70f8234360'
OLD_SHA = '751b031b17fc90e07404827c9f760443bc4ca205a3c545bb8556cebd33d9fc0a'
INIT_SHA = 'ebc6bb746aaf710d915c47036f92ce0c4ed23a185dfb5349b90e654bab7ba4ae'
STAGE = '/run/lynx/lynx-status-ext4.new'
TARGET = '/usr/local/bin/lynx-status'
BACKUP = '/root/lynx-rescue/lynx-status-before-ext4-v47.py'


def main():
    subprocess.run(['python3', '-m', 'py_compile', str(SOURCE)], check=True)
    data = SOURCE.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    os.umask(0o077)
    out = ROOT / 'logs' / f'v47-lynx-status-ext4-{time.time_ns()}'
    out.mkdir(mode=0o700)
    report = {'state': 'starting', 'boot_id': BOOT_ID, 'old_sha256': OLD_SHA,
              'new_sha256': digest, 'boot_partition_writes': False,
              'steps': []}
    backed_up = False

    def step(name, command, payload=None, timeout=25, port=2222):
        argv = ssh_command(IP, command)
        argv[-2:-2] = ['-p', str(port)]
        run = subprocess.run(argv, input=payload, capture_output=True,
                             timeout=timeout)
        (out / f'{name}.stdout').write_bytes(run.stdout)
        (out / f'{name}.stderr').write_bytes(run.stderr)
        report['steps'].append({
            'name': name, 'exit_code': run.returncode,
            'stdout_sha256': hashlib.sha256(run.stdout).hexdigest(),
            'stderr_sha256': hashlib.sha256(run.stderr).hexdigest()})
        if run.returncode:
            raise RuntimeError(f'{name} failed; inspect saved streams')
        return run.stdout.decode(errors='replace')

    try:
        step('rescue_identity',
             'set -eu; '
             f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{BOOT_ID}"; '
             f'test "$(sha256sum /init | cut -c1-64)" = "{INIT_SHA}"; '
             'printf LYNX_V47_RESCUE_VERIFIED', port=22)
        step('preflight',
             'set -eu; '
             f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{BOOT_ID}"; '
             f'test "$(sha256sum {TARGET} | cut -c1-64)" = "{OLD_SHA}"; '
             f'test ! -e {BACKUP}; test ! -e {STAGE}; '
             'test "$(df -Pm / | awk \'NR==2 {print $4}\')" -ge 350; '
             'for s in lynx-health lynx-battery-reserve lynx-local-logs '
             'lynx-wifi lynx-dropbear lynx-maintenance lynx-time-sync '
             'lynx-power-history; do /sbin/rc-service "$s" status >/dev/null; done; '
             'printf LYNX_STATUS_EXT4_READY')
        step('stage', f'cat > {STAGE}', payload=data)
        result = step('stage_live_test',
                      f'test "$(sha256sum {STAGE} | cut -c1-64)" = "{digest}"; '
                      f'python3 {STAGE} --assert-ready')
        state = json.loads(result)
        if state['schema'] != 2 or state['boot_id'] != BOOT_ID or state['issues']:
            raise RuntimeError('staged snapshot not ready')
        if state['root_filesystem'] != {
                'source': '/dev/sdc85', 'type': 'ext4', 'ext4_errors_count': 0}:
            raise RuntimeError('unexpected ext4 root evidence')
        step('backup',
             f'cp -p {TARGET} {BACKUP}; '
             f'test "$(sha256sum {BACKUP} | cut -c1-64)" = "{OLD_SHA}"')
        backed_up = True
        step('install',
             'set -eu; '
             f'test "$(sha256sum {TARGET} | cut -c1-64)" = "{OLD_SHA}"; '
             f'test "$(sha256sum {STAGE} | cut -c1-64)" = "{digest}"; '
             f'install -m 0755 {STAGE} {TARGET}.new; '
             f'mv {TARGET}.new {TARGET}; '
             f'test "$(sha256sum {TARGET} | cut -c1-64)" = "{digest}"')
        result = step('verify', f'{TARGET} --assert-ready')
        state = json.loads(result)
        if state['schema'] != 2 or state['boot_id'] != BOOT_ID or state['issues']:
            raise RuntimeError('installed snapshot not ready')
        report['snapshot'] = state
        report['state'] = 'v47-status-ext4-check-installed-and-proven'
    except Exception as exc:
        report.update(state='failed-or-incomplete', error=str(exc))
        if backed_up:
            try:
                step('restore_if_needed',
                     'set -eu; '
                     f'test "$(sha256sum {BACKUP} | cut -c1-64)" = "{OLD_SHA}"; '
                     f'current=$(sha256sum {TARGET} | cut -c1-64); '
                     f'case "$current" in {OLD_SHA}|{digest}) ;; *) exit 1;; esac; '
                     f'install -m 0755 {BACKUP} {TARGET}.new; '
                     f'mv {TARGET}.new {TARGET}')
            except Exception as restore_exc:
                report['restore_error'] = str(restore_exc)
    report['finished_ns'] = time.time_ns()
    result = out / 'result.json'
    result.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'state': report['state'], 'result': str(result)}))
    if report['state'] != 'v47-status-ext4-check-installed-and-proven':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
