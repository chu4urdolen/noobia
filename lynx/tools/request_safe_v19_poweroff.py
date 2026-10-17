"""Capture a pinned, health-checked power-off request before a fresh RAM trial.

No partition write. A successful SSH send proves only that power-off was
requested; physical shutdown is established by the user's observation.
"""
import argparse
import hashlib
import json
import os
import subprocess
import time
from pathlib import Path

from lynx_wifi_v19_contact import PROOF, proof_valid, ssh_command

ROOT = Path(__file__).resolve().parent.parent
PREFLIGHT = '''set -e
/bin/busybox sh /run/lynx/lynx-health-supervisor.sh --once
supplies=0
for p in /sys/class/power_supply/*; do
  [ -r "$p/online" ] || continue
  [ "$(cat "$p/online")" = 0 ]
  supplies=$((supplies+1))
done
[ "$supplies" -ge 1 ]
cat /run/lynx/battery-last
echo SAFE_POWEROFF_PREFLIGHT_PASS'''


def run(ip, out, name, command, timeout):
    with (out / (name + '.stdout')).open('wb') as stdout, \
            (out / (name + '.stderr')).open('wb') as stderr:
        try:
            child = subprocess.run(ssh_command(ip, command), stdout=stdout,
                                   stderr=stderr, timeout=timeout)
            rc = child.returncode
        except subprocess.TimeoutExpired:
            rc = None
    raw = (out / (name + '.stdout')).read_bytes()
    return raw, rc


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--session', type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--run', action='store_true')
    mode.add_argument('--preflight-only', action='store_true')
    parser.add_argument('--usb-unplugged-confirmed', action='store_true')
    args = parser.parse_args()
    if not (args.run or args.preflight_only):
        print('Use --preflight-only --session EXISTING_V19_RECEIPT for read-only checks, or --run with current unplugged confirmation after listener readiness. No phone contacted.')
        return
    if not args.session or (args.run and not args.usb_unplugged_confirmed):
        parser.error('Current pinned V19 session required; --run also needs unplugged confirmation')
    session = json.loads(args.session.read_text())
    if not (session.get('native_identity_verified') and session.get('session_left_running')):
        raise ValueError('Existing proven continuous V19 session required')
    os.umask(0o077)
    out = ROOT / 'logs' / ('safe-v19-poweroff-' + str(time.time_ns()))
    out.mkdir(mode=0o700)
    report = {'state': 'starting', 'started_ns': time.time_ns(),
              'session': str(args.session.resolve()), 'phone_ip': session['phone_ip'],
              'usb_unplugged_confirmed': bool(args.usb_unplugged_confirmed), 'partition_writes': False,
              'flash_performed': False, 'physical_shutdown_confirmed': False}
    def save():
        (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    save()
    try:
        proof, rc = run(session['phone_ip'], out, 'identity', PROOF, 8)
        if not proof_valid(proof.decode(errors='replace'), rc):
            raise ValueError('Pinned V19 identity failed before power-off')
        pre, rc = run(session['phone_ip'], out, 'preflight', PREFLIGHT, 10)
        if rc != 0 or b'LYNX_HEALTH_OK' not in pre or b'SAFE_POWEROFF_PREFLIGHT_PASS' not in pre:
            raise ValueError('Health or unplugged power-off preflight refused')
        report['health_preflight_sha256'] = hashlib.sha256(pre).hexdigest()
        if args.preflight_only:
            report['state'] = 'read-only-poweroff-preflight-passed'
            return
        report['state'] = 'requesting-poweroff'
        save()
        raw, rc = run(session['phone_ip'], out, 'poweroff-request',
                      '/bin/busybox poweroff -f', 8)
        report.update(state='poweroff-request-sent', poweroff_ssh_exit_code=rc,
                      poweroff_stdout_sha256=hashlib.sha256(raw).hexdigest())
    except Exception as exc:
        report.update(state='refused-before-poweroff', error=str(exc))
        raise
    finally:
        report['finished_ns'] = time.time_ns()
        save()
        print(json.dumps({'state': report['state'], 'result': str(out / 'result.json')}))


if __name__ == '__main__':
    main()
