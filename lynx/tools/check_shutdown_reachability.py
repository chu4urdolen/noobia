"""One bounded pinned SSH proof check; silence does not prove power-off.

No boot, fallback acknowledgement, flash, module load, or shutdown command.
The address is taken from the specified saved trial receipt, never scanned.
"""
import argparse
import hashlib
import ipaddress
import json
import os
import subprocess
import time
from pathlib import Path

from lynx_wifi_v19_contact import PROOF, proof_valid, ssh_command

ROOT = Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--trial-receipt', type=Path, required=True)
    args = parser.parse_args()
    trial = json.loads(args.trial_receipt.read_text())
    if not trial.get('native_identity_verified'):
        raise ValueError('Receipt must contain an earlier verified native identity')
    ip = trial['phone_ip']
    if ipaddress.ip_address(ip) not in ipaddress.ip_network('192.168.100.0/24'):
        raise ValueError('Address outside the established local handset network')
    os.umask(0o077)
    out = ROOT / 'logs' / ('shutdown-reachability-' + str(time.time_ns()))
    out.mkdir(mode=0o700)
    report = {'started_ns': time.time_ns(), 'phone_ip': ip,
              'source_receipt': str(args.trial_receipt.resolve()),
              'physical_poweroff_confirmed': False, 'identity_verified_now': False,
              'limits': 'A response proves the pinned native userspace is running. Silence can mean shutdown, a changed lease, Wi-Fi loss, or a kernel hang.'}
    command = ssh_command(ip, PROOF)
    command[command.index('ConnectTimeout=5')] = 'ConnectTimeout=3'
    try:
        p = subprocess.run(command, capture_output=True, timeout=4)
        stdout, stderr = p.stdout, p.stderr
        report.update(exit_code=p.returncode, timed_out=False,
                      identity_verified_now=proof_valid(stdout.decode(errors='replace'), p.returncode))
    except subprocess.TimeoutExpired as error:
        stdout, stderr = error.stdout or b'', error.stderr or b''
        report.update(exit_code=None, timed_out=True)
    for name, data in [('stdout', stdout), ('stderr', stderr)]:
        (out / name).write_bytes(data)
        report[name + '_sha256'] = hashlib.sha256(data).hexdigest()
        report[name + '_bytes'] = len(data)
    report['finished_ns'] = time.time_ns()
    (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'result': str(out / 'result.json'),
                      'identity_verified_now': report['identity_verified_now'],
                      'ssh_exit_code': report['exit_code'],
                      'physical_poweroff_confirmed': False}))


if __name__ == '__main__':
    main()
