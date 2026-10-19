"""Read-only compressed backup of the exact userdata region an ext4 trial would replace."""
import argparse
import gzip
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import subprocess
import time

from lynx_wifi_v19_contact import PROOF, proof_valid, ssh_command


ROOT = Path(__file__).resolve().parent.parent
SIZE = 1 << 30
EDGE = ROOT / 'backups/userdata-edges-1792413021056852842/result.json'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ip', default='192.168.100.4')
    args = parser.parse_args()
    if ipaddress.ip_address(args.ip) not in ipaddress.ip_network('192.168.100.0/24'):
        parser.error('IP must be on the isolated Noobia Wi-Fi')
    os.umask(0o077)
    out = ROOT / 'backups' / ('userdata-first-gib-' + str(time.time_ns()))
    out.mkdir(parents=True, mode=0o700)
    report = {'state': 'starting', 'created_ns': time.time_ns(),
              'device': '/dev/sdc85', 'offset_bytes': 0,
              'raw_bytes': SIZE, 'phone_writes': False, 'phone_mounts': False,
              'host_path': str(out / 'userdata-first-gib.img.gz')}

    def save():
        temp = out / 'result.tmp'
        temp.write_text(json.dumps(report, indent=2) + '\n')
        temp.replace(out / 'result.json')

    save()
    try:
        identity = subprocess.run(ssh_command(args.ip, PROOF),
                                  capture_output=True, timeout=15)
        if not proof_valid(identity.stdout.decode(errors='replace'), identity.returncode):
            raise ValueError('Pinned Lynx identity refused')
        preflight = '''set -eu
grep -Fx 'PARTNAME=userdata' /sys/class/block/sdc85/uevent >/dev/null
[ "$(cat /sys/class/block/sdc85/size)" = 466026432 ]
[ -b /dev/sdc85 ]
! grep -Eq '^/dev/sdc85 |^/dev/block/by-name/userdata ' /proc/mounts
[ "$(cat /run/lynx/health-bootstrap/ready)" = ready ]
/bin/busybox sh /run/lynx/lynx-health-supervisor.sh --once
cat /proc/sys/kernel/random/boot_id'''
        check = subprocess.run(ssh_command(args.ip, preflight),
                               capture_output=True, timeout=15)
        (out / 'preflight.stdout').write_bytes(check.stdout)
        (out / 'preflight.stderr').write_bytes(check.stderr)
        if check.returncode:
            raise ValueError('Partition or health preflight refused')
        boot_id = check.stdout.decode().strip().splitlines()[-1]
        report['boot_id'] = boot_id
        save()
        command = (f'[ "$(cat /proc/sys/kernel/random/boot_id)" = {boot_id} ] && '
                   '/bin/busybox dd if=/dev/sdc85 bs=1048576 count=1024 '
                   '2>/dev/null | /bin/busybox gzip -1')
        backup = out / 'userdata-first-gib.img.gz'
        with backup.open('wb') as stream:
            read = subprocess.run(ssh_command(args.ip, command),
                                  stdout=stream, stderr=subprocess.PIPE,
                                  timeout=600)
        (out / 'transfer.stderr').write_bytes(read.stderr)
        if read.returncode:
            raise ValueError('Read-only compressed transfer failed')
        report['compressed_bytes'] = backup.stat().st_size
        compressed = hashlib.sha256()
        raw = hashlib.sha256()
        first = hashlib.sha256()
        total = 0
        with backup.open('rb') as source:
            for block in iter(lambda: source.read(1048576), b''):
                compressed.update(block)
        with gzip.open(backup, 'rb') as source:
            for block in iter(lambda: source.read(1048576), b''):
                raw.update(block)
                if total < 16 * 1048576:
                    first.update(block[:16 * 1048576 - total])
                total += len(block)
        if total != SIZE:
            raise ValueError('Decompressed backup length differs')
        edge = json.loads(EDGE.read_text())
        head_sha = next(part['sha256'] for part in edge['parts']
                        if part['name'] == 'head')
        if first.hexdigest() != head_sha:
            raise ValueError('First 16 MiB differ from earlier bounded backup')
        report.update(raw_sha256=raw.hexdigest(),
                      compressed_sha256=compressed.hexdigest(),
                      first_16mib_sha256=head_sha,
                      state='verified-read-only-first-gib-backup')
    except Exception as error:
        report.update(state='failed', error=str(error))
    report['finished_ns'] = time.time_ns()
    save()
    print(json.dumps({'state': report['state'], 'result': str(out / 'result.json')}))
    if report['state'] != 'verified-read-only-first-gib-backup':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
