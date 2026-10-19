"""Guarded rollback of the first GiB from Lynx's verified eight-chunk backup."""
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
BACKUP = ROOT / 'backups/userdata-chunks-1792414534852012623/result.json'
BLOCK = 1048576


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--restore', action='store_true')
    parser.add_argument('--i-accept-rollback-write', action='store_true')
    parser.add_argument('--ip', default='192.168.100.4')
    args = parser.parse_args()
    if ipaddress.ip_address(args.ip) not in ipaddress.ip_network('192.168.100.0/24'):
        parser.error('IP must be on the isolated Noobia Wi-Fi')
    backup = json.loads(BACKUP.read_text())
    if (backup.get('state') != 'verified-read-only-first-gib-backup' or
            backup.get('raw_bytes') != 1 << 30 or
            backup.get('phone_writes') is not False or
            len(backup.get('chunks', [])) != 8):
        raise ValueError('Verified first-GiB backup missing')
    entries = sorted(backup['chunks'], key=lambda item: item['index'])
    for index, entry in enumerate(entries):
        path = Path(entry['path']).resolve(strict=True)
        if (entry['index'] != index or
                entry['offset_bytes'] != index * 128 * BLOCK or
                entry['bytes'] != 128 * BLOCK or
                entry['sha256'] != entry['phone_sha256'] or
                path.parent != BACKUP.parent):
            raise ValueError('Backup chunk inventory differs')
        digest = hashlib.sha256()
        total = 0
        with gzip.open(path, 'rb') as source:
            for block in iter(lambda: source.read(BLOCK), b''):
                digest.update(block)
                total += len(block)
        if total != 128 * BLOCK or digest.hexdigest() != entry['sha256']:
            raise ValueError('Backup chunk changed: ' + str(index))
    if not args.restore:
        print(json.dumps({'state': 'offline-rollback-inputs-verified',
                          'chunks': 8, 'bytes': 1 << 30,
                          'phone_contacted': False, 'phone_writes': False}))
        return
    if not args.i_accept_rollback_write:
        parser.error('--restore requires --i-accept-rollback-write')
    identity = subprocess.run(ssh_command(args.ip, PROOF),
                              capture_output=True, timeout=15)
    if not proof_valid(identity.stdout.decode(errors='replace'), identity.returncode):
        raise ValueError('Pinned V19 identity refused')
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
    if check.returncode:
        raise ValueError('Rollback phone preflight refused')
    boot_id = check.stdout.decode().strip().splitlines()[-1]
    os.umask(0o077)
    out = ROOT / 'logs' / ('userdata-first-gib-rollback-' + str(time.time_ns()))
    out.mkdir(mode=0o700)
    report = {'state': 'starting', 'started_ns': time.time_ns(),
              'device': '/dev/sdc85', 'offset_bytes': 0,
              'bytes': 1 << 30, 'backup_receipt': str(BACKUP),
              'boot_id': boot_id, 'phone_writes': False,
              'flash_performed': False, 'restored_chunks': []}

    def save():
        temp = out / 'result.tmp'
        temp.write_text(json.dumps(report, indent=2) + '\n')
        temp.replace(out / 'result.json')

    save()
    try:
        for entry in entries:
            index = entry['index']
            skip = index * 128
            report['state'] = 'rollback-write-in-progress'
            report['phone_writes'] = True
            save()
            command = (f'[ "$(cat /proc/sys/kernel/random/boot_id)" = {boot_id} ] && '
                       '/bin/busybox gzip -dc | /bin/busybox dd of=/dev/sdc85 '
                       f'bs={BLOCK} seek={skip} iflag=fullblock count=128 '
                       'conv=notrunc,fsync')
            with Path(entry['path']).open('rb') as source:
                sent = subprocess.run(ssh_command(args.ip, command), stdin=source,
                                      capture_output=True, timeout=300)
            (out / f'write-{index:02d}.stdout').write_bytes(sent.stdout)
            (out / f'write-{index:02d}.stderr').write_bytes(sent.stderr)
            if sent.returncode:
                raise ValueError('Rollback chunk write failed: ' + str(index))
            verify = (f'[ "$(cat /proc/sys/kernel/random/boot_id)" = {boot_id} ] && '
                      f'/bin/busybox dd if=/dev/sdc85 bs={BLOCK} skip={skip} '
                      'count=128 2>/dev/null | /bin/busybox sha256sum')
            checked = subprocess.run(ssh_command(args.ip, verify),
                                     capture_output=True, timeout=120)
            (out / f'verify-{index:02d}.stdout').write_bytes(checked.stdout)
            if checked.returncode or checked.stdout.decode().split()[0] != entry['sha256']:
                raise ValueError('Rollback chunk hash differs: ' + str(index))
            report['restored_chunks'].append(index)
            save()
        report['state'] = 'first-gib-restored-and-verified'
    except Exception as error:
        report.update(state='rollback-incomplete', error=str(error))
    report['finished_ns'] = time.time_ns()
    save()
    print(json.dumps({'state': report['state'], 'result': str(out / 'result.json')}))
    if report['state'] != 'first-gib-restored-and-verified':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
