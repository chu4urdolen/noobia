"""Test one supervised syslogd restart without disrupting SSH or safety guards."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
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
    out = ROOT / 'logs' / f'v46-local-logs-recovery-{time.time_ns()}'
    out.mkdir(mode=0o700)
    report = {'state': 'starting', 'boot_id': boot_id, 'phone_ip': ip,
              'verifications': [str(x) for x in paths],
              'boot_partition_writes': False, 'charging_changes': False,
              'probes': []}

    def call(name, command, timeout=12):
        argv = ssh_command(ip, command)
        argv[-2:-2] = ['-p', '2222']
        run = subprocess.run(argv, capture_output=True, timeout=timeout)
        (out / f'{name}.stdout').write_bytes(run.stdout)
        (out / f'{name}.stderr').write_bytes(run.stderr)
        report['probes'].append({'name': name, 'exit_code': run.returncode,
                                 'stdout_sha256': hashlib.sha256(run.stdout).hexdigest()})
        return run

    base = (f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{boot_id}" && '
            'test "$(readlink /proc/1/exe)" = /sbin/openrc-init')
    fallback = ('set -eu; ' + base + '; '
                'if /sbin/rc-service lynx-local-logs status >/dev/null 2>&1; then '
                'printf LYNX_LOGGER_RECOVERED; exit 0; fi; '
                '/sbin/rc-service lynx-local-logs restart; '
                '/sbin/rc-service lynx-local-logs status; '
                'printf LYNX_LOGGER_MANUAL_FALLBACK')
    try:
        preflight = call('preflight', 'set -eu; ' + base + '; '
                         'for service in lynx-health lynx-battery-reserve lynx-local-logs '
                         'lynx-wifi lynx-dropbear lynx-maintenance; do '
                         '/sbin/rc-service "$service" status >/dev/null; done; '
                         'printf LYNX_LOGGER_RECOVERY_READY')
        if preflight.returncode or b'LYNX_LOGGER_RECOVERY_READY' not in preflight.stdout:
            raise ValueError('Safety or logger preflight failed')
        stopped = call('stop_syslogd_worker', 'set -eu; ' + base + '; '
                       'pid=$(cat /run/lynx/lynx-syslogd.pid); '
                       'case "$pid" in ""|*[!0-9]*) exit 1;; esac; '
                       'tr "\\000" "\\n" < /proc/$pid/cmdline | grep -Fxq syslogd; '
                       'kill -TERM "$pid"; printf LYNX_SYSLOGD_STOPPED')
        if stopped.returncode or b'LYNX_SYSLOGD_STOPPED' not in stopped.stdout:
            raise ValueError('Controlled syslog worker stop refused')
        report['worker_stopped'] = True
        deadline = time.monotonic() + 75
        for number in range(1, 16):
            if time.monotonic() > deadline:
                break
            time.sleep(5)
            probe = call(f'recovery_probe_{number}', 'set -eu; ' + base + '; '
                         '/sbin/rc-service lynx-local-logs status >/dev/null; '
                         '/sbin/rc-service lynx-battery-reserve status >/dev/null; '
                         'printf LYNX_LOGGER_RECOVERED')
            if probe.returncode == 0 and b'LYNX_LOGGER_RECOVERED' in probe.stdout:
                report.update(state='v46-local-logs-auto-recovered', recovery_probe=number)
                break
        if report['state'] != 'v46-local-logs-auto-recovered':
            restored = call('manual_fallback', fallback, timeout=25)
            report['manual_fallback_succeeded'] = (
                restored.returncode == 0 and
                (b'LYNX_LOGGER_RECOVERED' in restored.stdout or
                 b'LYNX_LOGGER_MANUAL_FALLBACK' in restored.stdout))
            report['state'] = 'auto-recovery-not-observed'
    except Exception as error:
        report.update(state='failed-or-incomplete', error=str(error))
        if report.get('worker_stopped'):
            try:
                restored = call('manual_fallback_after_error', fallback, timeout=25)
                report['manual_fallback_succeeded'] = restored.returncode == 0
            except Exception as fallback_error:
                report['manual_fallback_error'] = str(fallback_error)
    report['finished_ns'] = time.time_ns()
    receipt = out / 'result.json'
    receipt.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'state': report['state'], 'result': str(receipt),
                      'recovery_probe': report.get('recovery_probe'),
                      'manual_fallback_succeeded': report.get('manual_fallback_succeeded')}))
    if report['state'] != 'v46-local-logs-auto-recovered':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
