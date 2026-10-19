"""Prove the V32 Alpine guard's closed-stdout failure on pinned Lynx SSH.

Only reads phone state and writes two small diagnostic streams to /run tmpfs.
No mount, phone partition write, handoff, reboot, or flash.
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import time

from lynx_wifi_v19_contact import PROOF, proof_valid, ssh_command

ROOT = Path(__file__).resolve().parent.parent
V32 = ROOT / 'linux-port/artifacts/persistent-openrc-v32-offline/build-result.json'


def remote(ip, command):
    return subprocess.run(ssh_command(ip, command), capture_output=True, timeout=15)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--contact-receipt', required=True, type=Path)
    args = parser.parse_args()
    contact_path = args.contact_receipt.resolve(strict=True)
    if not contact_path.is_relative_to(ROOT / 'logs'):
        raise ValueError('Contact receipt outside Lynx logs')
    contact = json.loads(contact_path.read_text())
    ip = contact.get('phone_ip', '')
    if (contact.get('state') != 'native-ssh-available' or
            contact.get('native_ssh_verified') is not True or
            not re.fullmatch(r'192\.168\.100\.[1-9][0-9]?', ip)):
        raise ValueError('Pinned contact receipt refused')
    build = json.loads(V32.read_text())
    os.umask(0o077)
    out = ROOT / 'logs' / ('pid1-stdio-diagnostic-' + str(time.time_ns()))
    out.mkdir(mode=0o700)
    report = {'state': 'starting', 'contact_receipt': str(contact_path),
              'phone_ip': ip, 'phone_partition_writes': False,
              'handoff_armed': False, 'flash_performed': False,
              'created_ns': time.time_ns()}
    try:
        proof = remote(ip, PROOF)
        if (not proof_valid(proof.stdout.decode(errors='replace'), proof.returncode) or
                build['init_sha256'] + '  /init' not in proof.stdout.decode(errors='replace')):
            raise ValueError('Current boot is not pinned V32 BusyBox')
        identity = remote(ip, '''set -e
cat /proc/sys/kernel/random/boot_id
for n in 0 1 2; do
    if [ -e "/proc/1/fd/$n" ]; then echo "FD$n=$(readlink "/proc/1/fd/$n")";
    else echo "FD$n=CLOSED"; fi
done
''')
        (out / 'pid1-fds.stdout').write_bytes(identity.stdout)
        (out / 'pid1-fds.stderr').write_bytes(identity.stderr)
        lines = identity.stdout.decode(errors='replace').splitlines()
        if identity.returncode or len(lines) != 4 or not re.fullmatch(
                r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', lines[0]):
            raise ValueError('PID 1 descriptor inventory failed')
        boot_id = lines[0]
        report.update(boot_id=boot_id, pid1_descriptors=lines[1:])
        guard = 'LYNX_OPENRC_AUTHORITY=host /bin/busybox sh /etc/lynx/openrc-handoff-guard.sh --check'
        closed = remote(ip, "/bin/busybox sh -c 'exec 1>&-; " + guard + "'")
        (out / 'closed.stdout').write_bytes(closed.stdout)
        (out / 'closed.stderr').write_bytes(closed.stderr)
        report['closed_stdout_guard_exit'] = closed.returncode
        prefix = '/run/lynx/stdio-probe-' + boot_id
        reopened = remote(ip, "/bin/busybox sh -c 'exec 0<&- 1>&- 2>&-; " +
                          'exec </dev/null 1>>' + prefix + '.stdout 2>>' + prefix +
                          '.stderr; ' + guard + "'")
        report['reopened_stdio_guard_exit'] = reopened.returncode
        streams = remote(ip, 'cat ' + prefix + '.stdout ' + prefix + '.stderr')
        (out / 'reopened.streams').write_bytes(streams.stdout)
        (out / 'reopened.read.stderr').write_bytes(streams.stderr)
        if (lines[2] != 'FD1=CLOSED' or closed.returncode == 0 or
                b'Bad file descriptor' not in closed.stderr or
                reopened.returncode != 0 or streams.returncode != 0 or
                b'OPENRC_HANDOFF_GUARD_PASS' not in streams.stdout):
            raise ValueError('Closed/reopened descriptor outcomes differ')
        report['state'] = 'closed-stdout-root-cause-proved'
    except Exception as error:
        report.update(state='failed-or-incomplete', error=str(error))
    report['finished_ns'] = time.time_ns()
    (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'state': report['state'], 'result': str(out / 'result.json')}))
    if report['state'] != 'closed-stdout-root-cause-proved':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
