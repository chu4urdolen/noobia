"""Pinned native SSH command with durable raw captures; no implicit shutdown."""
import argparse
import hashlib
import json
import os
import re
import subprocess
import time
from pathlib import Path

from lynx_wifi_v19_contact import PROOF, proof_valid, ssh_command

ROOT = Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--session', type=Path, required=True)
    parser.add_argument('--name', required=True)
    parser.add_argument('--command', required=True)
    parser.add_argument('--stdin-file', type=Path)
    parser.add_argument('--timeout', type=int, default=10)
    args = parser.parse_args()
    if not re.fullmatch('[a-z0-9-]+', args.name) or not 1 <= args.timeout <= 60:
        raise ValueError('Invalid capture name or timeout')
    session = json.loads(args.session.read_text())
    if not session.get('native_identity_verified') or not session.get('session_left_running'):
        raise ValueError('Needs a verified continuous-session receipt')
    os.umask(0o077)
    out = ROOT / 'logs' / ('live-' + args.name + '-' + str(time.time_ns()))
    out.mkdir(mode=0o700)
    report = {'started_ns': time.time_ns(), 'session': str(args.session.resolve()),
              'phone_ip': session['phone_ip'], 'operations': [], 'implicit_shutdown': False}

    def run(name, command, payload=None):
        op = {'name': name, 'command': command, 'started_ns': time.time_ns()}
        report['operations'].append(op)
        with (out / (name + '.stdout')).open('wb') as stdout, (out / (name + '.stderr')).open('wb') as stderr:
            try:
                p = subprocess.run(ssh_command(session['phone_ip'], command), input=payload,
                                   stdout=stdout, stderr=stderr, timeout=args.timeout)
                op['exit_code'] = p.returncode
            except subprocess.TimeoutExpired:
                op.update(exit_code=None, timed_out=True)
        data = (out / (name + '.stdout')).read_bytes()
        op.update(finished_ns=time.time_ns(), stdout_bytes=len(data), stdout_sha256=hashlib.sha256(data).hexdigest())
        (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
        return data, op['exit_code']

    raw, rc = run('identity', PROOF)
    report['native_identity_verified'] = proof_valid(raw.decode(errors='replace'), rc)
    if report['native_identity_verified']:
        _, rc = run('command', args.command, args.stdin_file.read_bytes() if args.stdin_file else None)
    report['finished_ns'] = time.time_ns()
    (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'result': str(out / 'result.json'), 'native_identity_verified': report['native_identity_verified'],
                      'command_exit_code': rc, 'capture': str(out / 'command.stdout')}))
    if not report['native_identity_verified'] or rc != 0:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
