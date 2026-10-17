"""Observe one V19 boot beacon and verify pinned SSH without changing Lynx.

This tool never acknowledges the boot fallback, loads modules, or requests a
reboot/poweroff. It is for short diagnosis, not for keeping a boot online.
"""
import argparse
import hashlib
import json
import os
import socket
import subprocess
import time
from pathlib import Path

from lynx_wifi_v19_contact import BUILD, PROOF, beacon_valid, proof_valid, ssh_command

ROOT = Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--listen', action='store_true')
    parser.add_argument('--seconds', type=int, default=240)
    args = parser.parse_args()
    if not args.listen:
        parser.error('Pass --listen to start the passive observer')
    if not 1 <= args.seconds <= 900:
        parser.error('--seconds must be between 1 and 900')

    os.umask(0o077)
    out = ROOT / 'logs' / ('identity-observer-' + str(time.time_ns()))
    out.mkdir(mode=0o700)
    receipt = out / 'result.json'
    report = {
        'state': 'starting', 'started_ns': time.time_ns(),
        'bind_ip': BUILD['collector_ip'], 'port': 5514,
        'deadline_seconds': args.seconds, 'events': [],
        'phone_contacted': False, 'native_identity_verified': False,
        'phone_write_issued': False, 'flash_performed': False,
        'power_command_issued': False,
    }

    def save():
        temporary = out / 'result.tmp'
        temporary.write_text(json.dumps(report, indent=2) + '\n')
        temporary.replace(receipt)

    save()
    start = time.monotonic()
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind((BUILD['collector_ip'], 5514))
        sock.settimeout(0.5)
        report['state'] = 'listening'
        report['ready_ns'] = time.time_ns()
        save()
        print('PASSIVE IDENTITY LISTENER READY:', receipt, flush=True)
        while time.monotonic() - start < args.seconds:
            report['heartbeat_ns'] = time.time_ns()
            save()
            try:
                data, address = sock.recvfrom(4096)
            except socket.timeout:
                continue
            ip = address[0]
            event = {
                'received_ns': time.time_ns(), 'source_ip': ip,
                'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
                'valid_beacon': beacon_valid(data, ip),
            }
            report['events'].append(event)
            save()
            (out / ('datagram-' + str(len(report['events'])) + '.bin')).write_bytes(data)
            if not event['valid_beacon']:
                continue
            report['phone_contacted'] = True
            event['ssh_started_ns'] = time.time_ns()
            save()
            try:
                result = subprocess.run(ssh_command(ip, PROOF), capture_output=True, timeout=15)
            except subprocess.TimeoutExpired as error:
                (out / 'ssh-timeout.raw').write_bytes((error.stdout or b'') + (error.stderr or b''))
                event['ssh_state'] = 'timeout'
                save()
                continue
            (out / ('ssh-' + str(len(report['events'])) + '.raw')).write_bytes(result.stdout + result.stderr)
            event.update(ssh_state='returned', ssh_exit_code=result.returncode,
                         ssh_finished_ns=time.time_ns())
            if proof_valid(result.stdout.decode(errors='replace'), result.returncode):
                report.update(state='identity-verified', native_identity_verified=True,
                              phone_ip=ip, verified_ns=time.time_ns())
                break
            save()
        else:
            report['state'] = 'discovery-deadline'
    report['finished_ns'] = time.time_ns()
    save()
    print(json.dumps({'result': str(receipt), 'state': report['state'],
                      'native_identity_verified': report['native_identity_verified']}))


if __name__ == '__main__':
    main()
