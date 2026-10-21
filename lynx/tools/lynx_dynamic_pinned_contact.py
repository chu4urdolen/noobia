"""Find Lynx on Noobia LAN, prove pinned BusyBox SSH, cancel fallback, save pstore.

This only contacts hosts whose public SSH key matches the saved Lynx pin.
No phone partition writes occur. Run before the timed Fastboot reboot.
"""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from find_lynx_pinned_ssh import NETWORK, pinned_key, probe
from lynx_wifi_v19_contact import BUILD, PROOF, proof_valid, ssh_command

ROOT = Path(__file__).resolve().parent.parent


def save(path, report):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(report, indent=2) + '\n')
    temp.replace(path)


async def open_ssh():
    semaphore = asyncio.Semaphore(80)
    addresses = ['192.168.100.6'] + [str(ip) for ip in NETWORK.hosts()
                                    if str(ip) != '192.168.100.6']
    found = await asyncio.gather(*(probe(ip, 22, semaphore) for ip in addresses))
    return [ip for item in found if item for ip, _ in [item]]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds', type=int, default=420)
    args = parser.parse_args()
    if not 1 <= args.seconds <= 900:
        parser.error('--seconds must be 1..900')
    os.umask(0o077)
    out = ROOT / 'logs' / ('dynamic-pinned-contact-' + str(time.time_ns()))
    out.mkdir(mode=0o700)
    receipt = out / 'result.json'
    report = {'state': 'scanning', 'started_ns': time.time_ns(),
              'session_token': BUILD['session_token'], 'native_ssh_verified': False,
              'fallback_cancel_ack_exit_code': None, 'network': str(NETWORK),
              'phone_partition_writes': False, 'attempts': [],
              'tool_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    save(receipt, report)
    print('DYNAMIC CONTACT READY:', receipt, flush=True)
    expected = pinned_key()
    deadline = time.monotonic() + args.seconds
    while time.monotonic() < deadline:
        for ip in asyncio.run(open_ssh()):
            attempt = {'ip': ip, 'at_ns': time.time_ns()}
            report['attempts'].append(attempt)
            save(receipt, report)
            try:
                key = subprocess.run(['ssh-keyscan', '-T', '2', '-p', '22', '-t',
                                      'ed25519', ip], capture_output=True,
                                     text=True, timeout=4)
                fields = [line.split() for line in key.stdout.splitlines()
                          if line and not line.startswith('#')]
                attempt['pinned_key_match'] = any(len(row) >= 3 and
                                                   row[1:3] == expected for row in fields)
                if not attempt['pinned_key_match']:
                    save(receipt, report)
                    continue
                proof = subprocess.run(ssh_command(ip, PROOF), capture_output=True,
                                       timeout=15)
                (out / 'identity.raw').write_bytes(proof.stdout + proof.stderr)
                attempt['identity_exit_code'] = proof.returncode
                if not proof_valid(proof.stdout.decode(errors='replace'), proof.returncode):
                    save(receipt, report)
                    continue
                report.update(state='identity-proved', native_ssh_verified=True,
                              phone_ip=ip, verified_ns=time.time_ns())
                save(receipt, report)
                token = BUILD['session_token']
                ack = "printf '%s\\n' '" + token + "' > /run/lynx/host-confirmed.tmp && mv /run/lynx/host-confirmed.tmp /run/lynx/host-confirmed"
                result = subprocess.run(ssh_command(ip, ack), capture_output=True,
                                        timeout=15)
                (out / 'ack.raw').write_bytes(result.stdout + result.stderr)
                report['fallback_cancel_ack_exit_code'] = result.returncode
                if result.returncode:
                    report['state'] = 'ack-failed'
                    save(receipt, report)
                    continue
                report.update(state='native-ssh-available', finished_ns=time.time_ns())
                save(receipt, report)
                # Read-only snapshot. Its failure does not invalidate contact.
                snapshot = ('printf "BOOT_ID\\n"; cat /proc/sys/kernel/random/boot_id; '
                            'printf "PSTORE\\n"; ls -l /sys/fs/pstore; '
                            'for f in /sys/fs/pstore/*; do [ -f "$f" ] && '
                            '{ printf "\\nFILE %s\\n" "$f"; cat "$f"; }; done; '
                            'printf "BOOT_LOG\\n"; cat /run/lynx/boot.log; true')
                try:
                    pstore = subprocess.run(ssh_command(ip, snapshot), capture_output=True,
                                            timeout=20)
                    (out / 'pstore-and-boot.raw').write_bytes(pstore.stdout + pstore.stderr)
                    report['pstore_snapshot_exit_code'] = pstore.returncode
                except subprocess.TimeoutExpired as error:
                    (out / 'pstore-and-boot.raw').write_bytes((error.stdout or b'') +
                                                             (error.stderr or b''))
                    report['pstore_snapshot_timed_out'] = True
                save(receipt, report)
                print('LYNX VERIFIED:', ip, receipt, flush=True)
                return
            except (OSError, subprocess.TimeoutExpired) as error:
                attempt['error'] = type(error).__name__
                save(receipt, report)
        time.sleep(2)
    report.update(state='deadline-without-verified-ssh', finished_ns=time.time_ns())
    save(receipt, report)
    print('NO PINNED CONTACT:', receipt, flush=True)


if __name__ == '__main__':
    main()
