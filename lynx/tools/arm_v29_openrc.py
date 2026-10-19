"""Arm V29's one-boot RAM handoff after pinned SSH and verified RAM health."""
import argparse
import hashlib
import json
import re
import subprocess
import time
from pathlib import Path

from lynx_wifi_v19_contact import BUILD, PROOF, proof_valid, ssh_command

ROOT = Path(__file__).resolve().parent.parent
BUILD_RESULT = ROOT / 'linux-port/artifacts/persistent-openrc-v29-offline/build-result.json'
V29 = ROOT / 'linux-port/artifacts/persistent-openrc-v29-offline/nord3-persistent-openrc-untested.img'
GUARD = ROOT / 'linux-port/openrc-handoff-guard.sh'


def load_receipt(path):
    path = path.resolve(strict=True)
    if not path.is_relative_to(ROOT / 'logs'):
        raise ValueError('Receipt is outside Lynx logs')
    return json.loads(path.read_text()), str(path)


def remote(ip, command, data=None, timeout=15):
    return subprocess.run(ssh_command(ip, command), input=data, capture_output=True, timeout=timeout)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--contact', type=Path, required=True)
    parser.add_argument('--health', type=Path, required=True)
    parser.add_argument('--arm', action='store_true')
    args = parser.parse_args()
    contact, contact_path = load_receipt(args.contact)
    health, health_path = load_receipt(args.health)
    build = json.loads(BUILD_RESULT.read_text())
    if (build.get('state') != 'offline-persistent-openrc-candidate-built' or
            hashlib.sha256(V29.read_bytes()).hexdigest() != build.get('image_sha256') or
            hashlib.sha256(GUARD.read_bytes()).hexdigest() !=
            build.get('script_sha256', {}).get('etc/lynx/openrc-handoff-guard.sh')):
        raise ValueError('V29 image or guard differs from reviewed build')
    if (contact.get('state') != 'native-ssh-available' or
            contact.get('native_ssh_verified') is not True or
            contact.get('fallback_cancel_ack_exit_code') != 0 or
            contact.get('session_token') != BUILD['session_token'] or
            not re.fullmatch(r'192\.168\.100\.[1-9][0-9]?', contact.get('phone_ip', ''))):
        raise ValueError('Pinned V29 contact receipt missing or differs')
    if (health.get('state') != 'local-health-in-ram-verified' or
            health.get('contact_receipt') != contact_path or
            health.get('phone_ip') != contact['phone_ip'] or
            health.get('usb_unplugged_confirmed') is not True):
        raise ValueError('Same-boot RAM health receipt missing or differs')
    if not args.arm:
        print(json.dumps({'state': 'ready-to-check-live-guard', 'phone_contacted': False,
                          'contact': contact_path, 'health': health_path}))
        return
    out = ROOT / 'logs' / ('v29-openrc-arm-' + str(time.time_ns()))
    out.mkdir(mode=0o700)
    report = {'state': 'starting', 'contact': contact_path, 'health': health_path,
              'image_sha256': build['image_sha256'], 'marker_written': False,
              'partition_writes': False, 'started_ns': time.time_ns()}
    receipt = out / 'result.json'
    def save():
        tmp = receipt.with_suffix('.tmp')
        tmp.write_text(json.dumps(report, indent=2) + '\n')
        tmp.replace(receipt)
    save()
    try:
        ip = contact['phone_ip']
        proof = remote(ip, PROOF)
        proof_text = proof.stdout.decode(errors='replace')
        if (not proof_valid(proof_text, proof.returncode) or
                build['init_sha256'] + '  /init' not in proof_text):
            raise ValueError('Fresh SSH proof does not identify V29')
        report['v29_identity_verified'] = True
        check = '''set -eu
test "$(cat /run/lynx/host-confirmed)" = "$(cat /etc/lynx/session-token)"
test -f /run/lynx/health-bootstrap/ready
test ! -e /run/lynx/openrc-handoff-ready
test -r /etc/lynx/openrc-handoff-guard.sh
test "$(readlink /proc/1/exe)" = /bin/busybox
LYNX_OPENRC_AUTHORITY=host LYNX_OPENRC_ARMING=1 /bin/busybox sh /etc/lynx/openrc-handoff-guard.sh --check
cat /proc/sys/kernel/random/boot_id
'''
        checked = remote(ip, check)
        checked_text = checked.stdout.decode(errors='replace')
        if checked.returncode or 'OPENRC_HANDOFF_GUARD_PASS' not in checked_text:
            raise ValueError('Live V29 health guard refused: ' + checked.stderr.decode(errors='replace')[-500:])
        boot_ids = re.findall(r'(?m)^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$', checked_text)
        if len(boot_ids) != 1:
            raise ValueError('Live boot ID missing')
        report.update(boot_id=boot_ids[0], guard_output=checked_text, state='guard-passed')
        save()
        # The marker exists only in tmpfs. PID 1 independently rechecks the
        # token, partition identity and live guard before its final exec.
        arm = '''set -eu
test ! -e /run/lynx/openrc-handoff-ready
test "$(cat /proc/sys/kernel/random/boot_id)" = "$1"
test "$(cat /run/lynx/host-confirmed)" = "$(cat /etc/lynx/session-token)"
LYNX_OPENRC_AUTHORITY=host LYNX_OPENRC_ARMING=1 /bin/busybox sh /etc/lynx/openrc-handoff-guard.sh --check >/dev/null
cat /etc/lynx/session-token > /run/lynx/openrc-handoff-ready.tmp
mv /run/lynx/openrc-handoff-ready.tmp /run/lynx/openrc-handoff-ready
echo V29_OPENRC_ARMED
'''
        armed = remote(ip, '/bin/busybox sh -s -- ' + boot_ids[0], arm.encode())
        if armed.returncode or b'V29_OPENRC_ARMED' not in armed.stdout:
            raise ValueError('Handoff marker not confirmed: ' + armed.stderr.decode(errors='replace')[-500:])
        report.update(state='v29-openrc-armed', marker_written=True, finished_ns=time.time_ns())
    except Exception as error:
        report.update(state='refused-or-failed', error=str(error), finished_ns=time.time_ns())
    save()
    print(json.dumps({'state': report['state'], 'result': str(receipt)}))
    if report['state'] != 'v29-openrc-armed':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
