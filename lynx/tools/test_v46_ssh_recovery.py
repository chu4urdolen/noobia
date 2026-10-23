"""Test one Alpine SSH worker recovery while retaining pinned rescue SSH."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import time

from lynx_wifi_v19_contact import ssh_command

ROOT = Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verification', required=True, type=Path)
    parser.add_argument('--maintenance-verification', required=True, type=Path)
    args = parser.parse_args()
    paths = [x.resolve(strict=True) for x in
             (args.verification, args.maintenance_verification)]
    if any(not x.is_relative_to(ROOT / 'logs') for x in paths):
        raise ValueError('Verification outside Lynx logs')
    boot, maintenance = [json.loads(x.read_text()) for x in paths]
    boot_id, ip = boot['boot_id'], boot['phone_ip']
    if (boot.get('state') != 'v46-autonomous-alpine-pid1-verified' or
            maintenance.get('state') != 'v46-maintenance-verified' or
            maintenance.get('boot_id') != boot_id or maintenance.get('phone_ip') != ip or
            not re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', boot_id) or
            not re.fullmatch(r'192\.168\.100\.[1-9][0-9]?', ip)):
        raise ValueError('Same-boot V46 maintenance verification missing')
    os.umask(0o077)
    out = ROOT / 'logs' / f'v46-ssh-recovery-{time.time_ns()}'
    out.mkdir(mode=0o700)
    report = {'state': 'starting', 'boot_id': boot_id, 'phone_ip': ip,
              'verifications': [str(x) for x in paths],
              'boot_partition_writes': False, 'rescue_ssh_preserved': True,
              'probes': []}

    def call(name, command, port=22, timeout=12):
        argv = ssh_command(ip, command)
        if port != 22:
            argv[-2:-2] = ['-p', str(port)]
        run = subprocess.run(argv, capture_output=True, timeout=timeout)
        (out / f'{name}.stdout').write_bytes(run.stdout)
        (out / f'{name}.stderr').write_bytes(run.stderr)
        report['probes'].append({'name': name, 'port': port, 'exit_code': run.returncode,
                                 'stdout_sha256': hashlib.sha256(run.stdout).hexdigest()})
        return run

    native_base = (f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{boot_id}" && '
                   'test "$(readlink /proc/1/exe)" = /sbin/openrc-init')
    rescue_base = (f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{boot_id}" && '
                   'test "$(readlink /proc/1/exe)" = /run/lynx/persistent-alpine/sbin/openrc-init && '
                   'test -d /run/lynx/persistent-alpine')
    recover_inside = (
        'set -eu; '
        'if /sbin/rc-service lynx-dropbear status >/dev/null 2>&1; then '
        'printf LYNX_SSH_RECOVERED; exit 0; fi; '
        'pidfile=/run/lynx/alpine-dropbear-2222.pid; '
        'if [ -r "$pidfile" ]; then pid=$(cat "$pidfile"); '
        'case "$pid" in ""|*[!0-9]*) exit 1;; esac; '
        'kill -0 "$pid" 2>/dev/null && exit 1; rm "$pidfile"; fi; '
        'netstat -lnt | grep -Eq ":2222[[:space:]]" && exit 1; '
        'address=$(ip -4 addr show dev wlan0 | sed -n '
        "'s/^[[:space:]]*inet \\(192\\.168\\.100\\.[0-9]*\\)\\/.*/\\1/p' | head -n 1); "
        'case "$address" in 192.168.100.*) ;; *) exit 1;; esac; '
        'test -s /etc/dropbear/lynx_ed25519_host_key; '
        'test -s /root/.ssh/authorized_keys; '
        '/usr/sbin/dropbear -E -s -j -k -p "$address:2222" -P "$pidfile" '
        '-r /etc/dropbear/lynx_ed25519_host_key </dev/null '
        '>>/run/lynx/alpine-dropbear-2222.log 2>&1; '
        'sleep 1; /sbin/rc-service lynx-dropbear status >/dev/null; '
        'printf LYNX_SSH_MANUAL_FALLBACK'
    )
    recover = ('set -eu; ' + rescue_base + '; /bin/busybox chroot '
               '/run/lynx/persistent-alpine /bin/sh -c ' + shlex.quote(recover_inside))
    try:
        native = call('native_preflight', 'set -eu; ' + native_base + '; '
                         '/sbin/rc-service lynx-maintenance status >/dev/null; '
                         '/sbin/rc-service lynx-battery-reserve status >/dev/null; '
                         '/sbin/rc-service lynx-local-logs status >/dev/null; '
                         '/sbin/rc-service lynx-dropbear status >/dev/null; '
                         'printf LYNX_NATIVE_READY', port=2222)
        if native.returncode or b'LYNX_NATIVE_READY' not in native.stdout:
            raise ValueError('Native Alpine or safety preflight failed')
        preflight = call('rescue_preflight', 'set -eu; ' + rescue_base + '; '
                         '/bin/busybox chroot /run/lynx/persistent-alpine '
                         '/sbin/rc-service lynx-maintenance status >/dev/null; '
                         'printf LYNX_RESCUE_READY')
        if preflight.returncode or b'LYNX_RESCUE_READY' not in preflight.stdout:
            raise ValueError('Rescue SSH or safety preflight failed')
        stopped = call('stop_alpine_ssh_worker', 'set -eu; ' + rescue_base + '; '
                       'pid=$(cat /run/lynx/alpine-dropbear-2222.pid); '
                       'case "$pid" in ""|*[!0-9]*) exit 1;; esac; '
                       'tr "\\000" "\\n" < /proc/$pid/cmdline | grep -Fxq /usr/sbin/dropbear; '
                       'kill -TERM "$pid"; printf LYNX_ALPINE_SSH_STOPPED')
        if stopped.returncode or b'LYNX_ALPINE_SSH_STOPPED' not in stopped.stdout:
            raise ValueError('Controlled worker stop refused')
        report['worker_stopped'] = True
        deadline = time.monotonic() + 70
        for number in range(1, 15):
            if time.monotonic() > deadline:
                break
            time.sleep(5)
            probe = call(f'recovery_probe_{number}',
                         'set -eu; ' + native_base + '; '
                         '/sbin/rc-service lynx-dropbear status >/dev/null; '
                         'printf LYNX_SSH_RECOVERED', port=2222, timeout=10)
            if probe.returncode == 0 and b'LYNX_SSH_RECOVERED' in probe.stdout:
                report.update(state='v46-alpine-ssh-auto-recovered',
                              recovery_probe=number)
                break
        else:
            report['state'] = 'auto-recovery-not-observed'
        if report['state'] != 'v46-alpine-ssh-auto-recovered':
            fallback = call('manual_fallback', recover)
            if fallback.returncode == 0 and (b'LYNX_SSH_RECOVERED' in fallback.stdout or
                                             b'LYNX_SSH_MANUAL_FALLBACK' in fallback.stdout):
                report['manual_fallback_succeeded'] = True
            else:
                report['manual_fallback_succeeded'] = False
    except Exception as error:
        report.update(state='failed-or-incomplete', error=str(error))
        if report.get('worker_stopped'):
            try:
                fallback = call('manual_fallback_after_error', recover)
                report['manual_fallback_succeeded'] = fallback.returncode == 0
            except Exception as fallback_error:
                report['manual_fallback_error'] = str(fallback_error)
    report['finished_ns'] = time.time_ns()
    receipt = out / 'result.json'
    receipt.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'state': report['state'], 'result': str(receipt),
                      'recovery_probe': report.get('recovery_probe'),
                      'manual_fallback_succeeded': report.get('manual_fallback_succeeded')}))
    if report['state'] != 'v46-alpine-ssh-auto-recovered':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
