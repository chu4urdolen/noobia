"""Arm V21's RAM-only OpenRC gate after current power and native identity checks.

Without --arm this is a local receipt audit. Arming contacts Lynx over pinned
SSH and writes only /run/lynx/openrc-handoff-ready for the current boot.
"""
import argparse
import hashlib
import json
import re
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PORT = ROOT / 'linux-port'
BASE = PORT / 'artifacts/busybox-wifi-ssh-twostage-v19'
CANDIDATE = PORT / 'artifacts/openrc-gated-v21-fastboot-timeout'
GUARD = PORT / 'openrc-handoff-guard.sh'
KERNEL = '5.10.149-android12-9-o-g311738fbb5a8'
BB_SHA = '999cb969d09093a71716cfc747bb53cdada3f332c05eb5046c56e0f66a4d6d22'


def ssh_command(ip, command):
    return ['ssh', '-o', 'BatchMode=yes', '-o', 'IdentitiesOnly=yes',
            '-o', 'StrictHostKeyChecking=yes', '-o', 'GlobalKnownHostsFile=/dev/null',
            '-o', 'HostKeyAlias=lynx', '-o', 'UserKnownHostsFile=' + str(ROOT / 'secrets/lynx_known_hosts'),
            '-o', 'ConnectTimeout=5', '-i', str(ROOT / 'secrets/nexus_lynx_ed25519'),
            'root@' + ip, command]


def audit(session_path, power_path):
    build = json.loads((BASE / 'build-validation.json').read_text())
    candidate = json.loads((CANDIDATE / 'build-result.json').read_text())
    image = (CANDIDATE / 'nord3-openrc-gated-candidate.img').read_bytes()
    session = json.loads(session_path.read_text())
    power = json.loads(power_path.read_text())
    require = lambda ok, msg: (_ for _ in ()).throw(ValueError(msg)) if not ok else None
    require(candidate.get('state') == 'offline-openrc-gated-candidate-built', 'Candidate receipt is not verified')
    require(candidate.get('parent_v19_sha256') == build.get('candidate_sha256'), 'Candidate parent differs from V19')
    require(hashlib.sha256(image).hexdigest() == candidate.get('candidate_sha256'), 'Candidate image hash differs')
    require(hashlib.sha256(GUARD.read_bytes()).hexdigest() == candidate.get('handoff_guard_sha256'), 'Handoff guard differs from candidate')
    require(session.get('state') == 'native-ssh-available' and session.get('native_ssh_verified'), 'Current native SSH receipt required')
    require(session.get('session_token') == build.get('session_token'), 'Boot token differs from the candidate')
    ip = session.get('phone_ip', '')
    require(re.fullmatch(r'192\.168\.100\.(?:[1-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-4])', ip) is not None,
            'Phone IP is outside the pinned Lynx network')
    require(power.get('state') == 'ready' and power.get('mode') == 'apply' and power.get('native_identity_verified'),
            'Successful runtime-power apply receipt required')
    require(re.fullmatch(r'[0-9a-f-]{36}', power.get('boot_id', '')) is not None, 'Runtime power boot ID is missing')
    return build, candidate, session, power


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--session', type=Path, required=True)
    parser.add_argument('--runtime-power', type=Path, required=True)
    parser.add_argument('--arm', action='store_true')
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    build, candidate, session, power = audit(args.session, args.runtime_power)
    if args.self_test:
        proof = ('LYNX_NATIVE_SSH_PROOF\n' + KERNEL + '\n/bin/busybox\n' +
                 candidate['init_sha256'] + '  /init\n' + BB_SHA + '  /bin/busybox\n' +
                 build['session_token'] + '\nuid=0(root)\n' + power['boot_id'] + '\n')
        assert candidate['init_sha256'] + '  /init' in proof
        assert build['session_token'] in proof
        marker_token = build['session_token']
        assert re.fullmatch('[0-9a-f]{32}', marker_token)
        assert not args.arm
        print('Receipt pairing and token checks passed; no phone contacted or marker written.')
        return
    if not args.arm:
        print('Receipts are structurally paired. Add --arm to perform fresh pinned SSH checks and write the one-boot handoff marker.')
        return

    token = build['session_token']
    proof_command = ("printf 'LYNX_NATIVE_SSH_PROOF\\n'; uname -r; readlink /proc/1/exe; "
                     "sha256sum /init /bin/busybox; cat /etc/lynx/session-token; id; "
                     "cat /proc/sys/kernel/random/boot_id")
    started = time.time_ns()
    out = ROOT / 'logs' / ('openrc-handoff-arm-' + str(started))
    out.mkdir(mode=0o700)
    report = {'state': 'starting', 'created_ns': started, 'session': str(args.session.resolve()),
              'runtime_power_receipt': str(args.runtime_power.resolve()), 'phone_ip': session['phone_ip'],
              'candidate_sha256': candidate['candidate_sha256'], 'flash_performed': False,
              'boot_or_partition_changed': False, 'marker_written': False}
    (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    def run(command, payload=None):
        return subprocess.run(ssh_command(session['phone_ip'], command), input=payload,
                              capture_output=True, timeout=20)
    try:
        identity = run(proof_command)
        text = identity.stdout.decode(errors='replace')
        checks = ['LYNX_NATIVE_SSH_PROOF\n', KERNEL + '\n', '/bin/busybox\n',
                  candidate['init_sha256'] + '  /init', BB_SHA + '  /bin/busybox',
                  token + '\n', 'uid=0(root)', power['boot_id'] + '\n']
        if identity.returncode or any(value not in text for value in checks):
            raise ValueError('Fresh pinned native identity or boot ID did not match')
        require_guard = "test \"$(cat /run/lynx/host-confirmed)\" = '" + token + "' && test ! -e /run/lynx/openrc-handoff-ready"
        finish = ("\nLYNX_OPENRC_ARMING=1 lynx_openrc_handoff_guard\n" +
                  "printf '%s\\n' '" + token + "' > /run/lynx/openrc-handoff-ready.tmp\n" +
                  "mv /run/lynx/openrc-handoff-ready.tmp /run/lynx/openrc-handoff-ready\n" +
                  "cat /run/lynx/openrc-handoff-ready\n")
        script = ("set -eu\n" + require_guard + "\n" + GUARD.read_text() + finish).encode()
        armed = run('sh -s', script)
        output = armed.stdout.decode(errors='replace')
        if armed.returncode or 'OPENRC_HANDOFF_GUARD_PASS' not in output or token + '\n' not in output:
            raise ValueError('Live safety guard refused handoff; marker not confirmed')
        report.update(state='openrc-handoff-armed-for-current-boot', marker_written=True,
                      boot_id=power['boot_id'], guard_output=output,
                      remote_stderr=armed.stderr.decode(errors='replace'), finished_ns=time.time_ns())
    except Exception as error:
        report.update(state='refused-or-failed', error=str(error), finished_ns=time.time_ns())
    (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'state': report['state'], 'result': str(out / 'result.json')}, indent=2))
    if report['state'] != 'openrc-handoff-armed-for-current-boot':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
