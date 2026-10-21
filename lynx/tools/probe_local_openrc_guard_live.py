"""Probe V34's local OpenRC guard read-only on a healthy V33 boot."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time

from lynx_wifi_v19_contact import BUILD, PROOF, proof_valid, ssh_command

ROOT = Path(__file__).resolve().parent.parent
V33 = json.loads((ROOT / 'linux-port/artifacts/persistent-openrc-v33-offline/build-result.json').read_text())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--contact', required=True, type=Path)
    parser.add_argument('--arm', required=True, type=Path)
    args = parser.parse_args()
    contact_path = args.contact.resolve(strict=True)
    arm_path = args.arm.resolve(strict=True)
    if not all(p.is_relative_to(ROOT / 'logs') for p in (contact_path, arm_path)):
        raise ValueError('Receipt escaped Lynx logs')
    contact, arm = (json.loads(p.read_text()) for p in (contact_path, arm_path))
    if (contact.get('state') != 'native-ssh-available' or
            contact.get('native_ssh_verified') is not True or
            contact.get('session_token') != BUILD['session_token'] or
            arm.get('state') != 'v33-openrc-armed' or
            arm.get('contact') != str(contact_path)):
        raise ValueError('Same-boot pinned V33 receipts differ')
    ip = contact['phone_ip']
    os.umask(0o077)
    out = ROOT / 'logs' / ('local-openrc-guard-probe-' + str(time.time_ns()))
    out.mkdir(mode=0o700)
    receipt = out / 'result.json'
    report = {'state': 'starting', 'created_ns': time.time_ns(),
              'contact': str(contact_path), 'arm': str(arm_path),
              'phone_ip': ip, 'phone_partition_writes': False,
              'phone_ram_writes': False}

    def save():
        temp = receipt.with_suffix('.tmp')
        temp.write_text(json.dumps(report, indent=2) + '\n')
        temp.replace(receipt)

    save()
    proof = subprocess.run(ssh_command(ip, PROOF), capture_output=True, timeout=12)
    (out / 'identity.raw').write_bytes(proof.stdout + proof.stderr)
    if (not proof_valid(proof.stdout.decode(errors='replace'), proof.returncode) or
            V33['init_sha256'].encode() + b'  /init' not in proof.stdout):
        raise ValueError('Live identity does not identify V33')
    command = '''set -eu
test "$(cat /proc/sys/kernel/random/boot_id)" = "$1"
test "$(readlink /proc/1/exe)" = /run/lynx/persistent-alpine/sbin/openrc-init
test "$(cat /run/lynx/health-bootstrap/ready)" = ready
test "$(cat /run/lynx/local-boot-ready)" = "$(cat /etc/lynx/session-token)"
LYNX_OPENRC_AUTHORITY=local /bin/busybox sh /etc/lynx/openrc-handoff-guard.sh --check
echo LOCAL_GUARD_LIVE_PROBE_PASS
'''
    result = subprocess.run(ssh_command(ip, '/bin/busybox sh -s -- ' + arm['boot_id']),
                            input=command.encode(), capture_output=True, timeout=20)
    (out / 'probe.stdout').write_bytes(result.stdout)
    (out / 'probe.stderr').write_bytes(result.stderr)
    report.update(exit_code=result.returncode,
                  state=('local-guard-live-probe-passed' if result.returncode == 0 and
                         b'OPENRC_HANDOFF_GUARD_PASS' in result.stdout and
                         b'LOCAL_GUARD_LIVE_PROBE_PASS' in result.stdout
                         else 'local-guard-live-probe-refused'),
                  finished_ns=time.time_ns())
    save()
    print(json.dumps({'state': report['state'], 'result': str(receipt)}))
    if report['state'] != 'local-guard-live-probe-passed':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
