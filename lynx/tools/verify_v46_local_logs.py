"""Verify Lynx's bounded on-device syslog and kernel log capture."""

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
SOURCE = ROOT / 'linux-port/openrc-lynx-local-logs'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verification', required=True, type=Path)
    args = parser.parse_args()
    path = args.verification.resolve(strict=True)
    if not path.is_relative_to(ROOT / 'logs'):
        raise ValueError('Verification outside Lynx logs')
    proof = json.loads(path.read_text())
    boot_id, ip = proof['boot_id'], proof['phone_ip']
    if (proof.get('state') != 'v46-autonomous-alpine-pid1-verified' or
            not re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', boot_id) or
            not re.fullmatch(r'192\.168\.100\.[1-9][0-9]?', ip)):
        raise ValueError('V46 same-boot verification missing')
    marker = f'LYNX_LOG_PROOF_{time.time_ns()}'
    digest = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    command = (
        'set -eu; '
        f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{boot_id}"; '
        f'test "$(sha256sum /etc/init.d/lynx-local-logs | cut -c1-64)" = "{digest}"; '
        'test "$(readlink -f /etc/runlevels/default/lynx-local-logs)" = /etc/init.d/lynx-local-logs; '
        '/sbin/rc-service lynx-local-logs status >/dev/null; '
        'test "$(stat -c %a /var/log/lynx)" = 700; '
        'test "$(awk \'$2=="/" {print $3; exit}\' /proc/mounts)" = ext4; '
        f'/bin/busybox logger -p daemon.err -t lynx-proof "{marker}"; '
        f'printf "<3>{marker}_KERNEL\\n" > /dev/kmsg; '
        f'/bin/busybox logger -p daemon.warning -t lynx-proof "{marker}_FILTERED"; '
        f'printf "<4>{marker}_KERNEL_FILTERED\\n" > /dev/kmsg; '
        'sleep 2; '
        f'grep -Fq "{marker}" /var/log/lynx/messages; '
        f'grep -Fq "{marker}_KERNEL" /var/log/lynx/messages; '
        f'! grep -Fq "{marker}_FILTERED" /var/log/lynx/messages; '
        f'! grep -Fq "{marker}_KERNEL_FILTERED" /var/log/lynx/messages; '
        'test "$(stat -c %s /var/log/lynx/messages)" -le 524288; '
        'if [ -r /run/lynx/boot.log ]; then test -r /var/log/lynx/boot-' + boot_id + '.log; fi; '
        'printf LYNX_LOCAL_LOGS_VERIFIED'
    )
    argv = ssh_command(ip, command)
    argv[-2:-2] = ['-p', '2222']
    os.umask(0o077)
    out = ROOT / 'logs' / f'v46-local-logs-verify-{time.time_ns()}'
    out.mkdir(mode=0o700)
    report = {'state': 'starting', 'boot_id': boot_id, 'phone_ip': ip,
              'verification': str(path), 'service_sha256': digest,
              'read_only_except_test_messages': True, 'marker': marker}
    try:
        run = subprocess.run(argv, capture_output=True, timeout=20)
        (out / 'stdout').write_bytes(run.stdout)
        (out / 'stderr').write_bytes(run.stderr)
        if run.returncode or b'LYNX_LOCAL_LOGS_VERIFIED' not in run.stdout:
            raise ValueError('Persistent logger proof failed')
        report['state'] = 'v46-local-logs-verified'
    except Exception as error:
        report.update(state='failed-or-incomplete', error=str(error))
    report['finished_ns'] = time.time_ns()
    result = out / 'result.json'
    result.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'state': report['state'], 'result': str(result)}))
    if report['state'] != 'v46-local-logs-verified':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
