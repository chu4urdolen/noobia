"""Sample the frozen OpenRC safety guard on a pinned BusyBox SSH boot.

Read-only on device apart from staging the guard in tmpfs. Never arms a
handoff, mounts storage, changes PID 1, or writes a phone partition.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time

from lynx_wifi_v19_contact import PROOF, proof_valid, ssh_command


ROOT = Path(__file__).resolve().parent.parent
GUARD = ROOT / 'linux-port/openrc-handoff-guard.sh'
BUILD = ROOT / 'linux-port/artifacts/persistent-openrc-v29-offline/build-result.json'


def remote(ip, command, data=None, timeout=20):
    return subprocess.run(ssh_command(ip, command), input=data,
                          capture_output=True, timeout=timeout)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--contact-receipt', required=True, type=Path)
    parser.add_argument('--samples', type=int, default=20)
    args = parser.parse_args()
    if not 1 <= args.samples <= 40:
        raise ValueError('samples must be 1..40')
    receipt = args.contact_receipt.resolve(strict=True)
    if not receipt.is_relative_to(ROOT / 'logs'):
        raise ValueError('contact receipt is outside Lynx logs')
    contact = json.loads(receipt.read_text())
    ip = contact.get('phone_ip', '')
    if (contact.get('state') != 'native-ssh-available' or
            contact.get('native_ssh_verified') is not True or
            not re.fullmatch(r'192\.168\.100\.[1-9][0-9]?', ip)):
        raise ValueError('pinned contact receipt refused')
    build = json.loads(BUILD.read_text())
    source = GUARD.read_bytes()
    expected = build['script_sha256']['etc/lynx/openrc-handoff-guard.sh']
    if hashlib.sha256(source).hexdigest() != expected:
        raise ValueError('guard differs from reviewed V29 source')
    os.umask(0o077)
    out = ROOT / 'logs' / ('openrc-guard-live-' + str(time.time_ns()))
    out.mkdir(mode=0o700)
    report = {'state': 'starting', 'contact_receipt': str(receipt),
              'phone_ip': ip, 'guard_sha256': expected, 'samples_requested': args.samples,
              'partition_writes': False, 'pid1_changed': False,
              'created_ns': time.time_ns()}
    try:
        proof = remote(ip, PROOF)
        if not proof_valid(proof.stdout.decode(errors='replace'), proof.returncode):
            raise ValueError('pinned SSH identity refused')
        preflight = remote(ip, '''set -eu
test -f /run/lynx/health-bootstrap/ready
test "$(cat /run/lynx/health-bootstrap/ready)" = ready
test "$(readlink /proc/1/exe)" = /bin/busybox
cat /proc/sys/kernel/random/boot_id
''')
        if preflight.returncode:
            raise ValueError('health or PID 1 preflight refused')
        boot_id = preflight.stdout.decode().strip()
        if not re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', boot_id):
            raise ValueError('invalid boot ID')
        if contact.get('boot_id') and contact['boot_id'] != boot_id:
            raise ValueError('contact receipt belongs to an earlier boot')
        uploaded = remote(ip, 'cat > /run/lynx/openrc-handoff-guard.sh', source)
        if uploaded.returncode:
            raise ValueError('RAM guard staging failed')
        checked = remote(ip, '/bin/busybox sha256sum /run/lynx/openrc-handoff-guard.sh')
        if checked.returncode or checked.stdout.decode().strip() != expected + '  /run/lynx/openrc-handoff-guard.sh':
            raise ValueError('RAM guard hash differs')
        script = '''set -u
test "$(cat /proc/sys/kernel/random/boot_id)" = "$1" || exit 90
i=0
while [ "$i" -lt "$2" ]; do
    i=$((i+1))
    LYNX_OPENRC_AUTHORITY=host LYNX_OPENRC_ARMING=1 /bin/busybox sh /run/lynx/openrc-handoff-guard.sh --check
    code=$?
    echo "GUARD_SAMPLE_EXIT $i $code"
    sleep 0.2
done
'''
        trial = remote(ip, '/bin/busybox sh -s -- ' + boot_id + ' ' + str(args.samples),
                       script.encode(), timeout=120)
        (out / 'samples.stdout').write_bytes(trial.stdout)
        (out / 'samples.stderr').write_bytes(trial.stderr)
        exits = [int(v) for v in re.findall(rb'(?m)^GUARD_SAMPLE_EXIT \d+ (\d+)$', trial.stdout)]
        report.update(boot_id=boot_id, sample_exit_codes=exits,
                      samples_completed=len(exits), refused_count=sum(v != 0 for v in exits),
                      trial_exit_code=trial.returncode)
        if trial.returncode or len(exits) != args.samples:
            raise ValueError('guard sample run incomplete')
        report['state'] = 'guard-samples-complete'
    except Exception as error:
        report.update(state='failed-or-incomplete', error=str(error))
    report['finished_ns'] = time.time_ns()
    (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'state': report['state'], 'result': str(out / 'result.json'),
                      'refused_count': report.get('refused_count')}))
    if report['state'] != 'guard-samples-complete':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
