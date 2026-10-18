"""Capture Lynx's LK-identified expdb log prefix over pinned V19 SSH.

Reads only /dev/sdc7 after exact expdb name and 128 MiB size checks. No mount,
partition write, authentication bypass, or reboot. Raw output remains private.
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
CAPTURE_BYTES = 0xF0000
COMMAND = ("set -eu; "
           "grep -Fx PARTNAME=expdb /sys/class/block/sdc7/uevent >/dev/null; "
           "grep -Fx DEVNAME=sdc7 /sys/class/block/sdc7/uevent >/dev/null; "
           "test \"$(/bin/busybox blockdev --getsize64 /dev/sdc7)\" = 134217728; "
           "/bin/busybox dd if=/dev/sdc7 bs=4096 count=240")


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--contact-receipt', type=Path)
    parser.add_argument('--capture', action='store_true')
    args = parser.parse_args()
    if not args.capture:
        print(json.dumps({'state': 'offline-plan', 'read_bytes': CAPTURE_BYTES,
                          'device': '/dev/sdc7', 'phone_contacted': False,
                          'partition_writes': False,
                          'requires_fresh_v19_contact_receipt': True}))
        return
    if args.contact_receipt is None:
        parser.error('--capture requires --contact-receipt')
    receipt = args.contact_receipt.resolve(strict=True)
    if not receipt.is_relative_to(ROOT / 'logs'):
        raise ValueError('Contact receipt escaped Lynx logs')
    contact = json.loads(receipt.read_text())
    if not (contact.get('state') == 'native-ssh-available' and
            contact.get('native_ssh_verified') and
            contact.get('fallback_cancel_ack_exit_code') == 0 and
            contact.get('phone_ip')):
        raise ValueError('Proven V19 contact receipt required')
    os.umask(0o077)
    out = ROOT / 'logs' / ('expdb-prefix-' + str(time.time_ns()))
    out.mkdir(mode=0o700)
    report = {'state': 'starting', 'created_ns': time.time_ns(),
              'contact_receipt': str(receipt), 'phone_ip': contact['phone_ip'],
              'read_bytes': CAPTURE_BYTES, 'partition_writes': False,
              'flash_performed': False, 'reboot_issued': False}
    def save():
        temporary = out / 'result.tmp'
        temporary.write_text(json.dumps(report, indent=2) + '\n')
        temporary.replace(out / 'result.json')
    save()
    try:
        identity = subprocess.run(ssh_command(contact['phone_ip'], PROOF),
                                  capture_output=True, timeout=15)
        (out / 'identity.stdout').write_bytes(identity.stdout)
        (out / 'identity.stderr').write_bytes(identity.stderr)
        if not proof_valid(identity.stdout.decode(errors='replace'), identity.returncode):
            raise ValueError('Pinned native V19 identity failed')
        report['native_identity_verified'] = True
        boot = subprocess.run(ssh_command(contact['phone_ip'],
                              'cat /proc/sys/kernel/random/boot_id'),
                              capture_output=True, timeout=15)
        (out / 'boot-id.stdout').write_bytes(boot.stdout)
        (out / 'boot-id.stderr').write_bytes(boot.stderr)
        boot_id = boot.stdout.decode(errors='replace').strip()
        if boot.returncode or not re.fullmatch(
                r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',
                boot_id):
            raise ValueError('Boot ID unavailable')
        report['boot_id'] = boot_id
        save()
        raw = out / 'expdb-first-0xf0000.raw'
        with raw.open('wb') as stdout, (out / 'read.stderr').open('wb') as stderr:
            read = subprocess.run(ssh_command(contact['phone_ip'], COMMAND),
                                  stdout=stdout, stderr=stderr, timeout=30)
        if read.returncode or raw.stat().st_size != CAPTURE_BYTES:
            raise ValueError('Expdb read incomplete or identity guard refused')
        report.update(state='read-only-capture-complete', capture=str(raw),
                      sha256=digest(raw), finished_ns=time.time_ns())
    except Exception as error:
        report.update(state='failed', error=str(error), finished_ns=time.time_ns())
    save()
    print(json.dumps({'state': report['state'], 'result': str(out / 'result.json'),
                      'sha256': report.get('sha256')}))
    if report['state'] != 'read-only-capture-complete':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
