"""Guarded first-GiB userdata install; --prepare is read-only."""
import argparse
import gzip
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import subprocess
import time

from lynx_wifi_v19_contact import PROOF, proof_valid, ssh_command


ROOT = Path(__file__).resolve().parent.parent
IMAGE_DIR = ROOT / 'linux-port/artifacts/persistent-alpine-ext4-1792413794183987933'
IMAGE = IMAGE_DIR / 'alpine-openrc-root-1GiB.ext4'
COMPRESSED = IMAGE_DIR / 'alpine-openrc-root-1GiB.ext4.gz'
BACKUP = ROOT / 'backups/userdata-chunks-1792414534852012623/result.json'
V19 = ROOT / 'linux-port/artifacts/busybox-wifi-ssh-twostage-v19/nord3-busybox-candidate.img'
V19_SHA = '5ce2dbf8a7c132fa7e31f6be70aa76f83afe8c293e2cd5f02251a532486fd851'
SIZE = 1 << 30


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def local_audit():
    image = json.loads((IMAGE_DIR / 'result.json').read_text())
    backup = json.loads(BACKUP.read_text())
    if (image.get('state') != 'offline-ext4-root-image-verified' or
            image.get('phone_contacted') is not False or
            image.get('phone_partition_writes') is not False or
            image.get('image_bytes') != SIZE or
            image.get('image_sha256') != sha(IMAGE) or
            image.get('compressed_sha256') != sha(COMPRESSED) or
            image.get('compressed_bytes') != COMPRESSED.stat().st_size or
            backup.get('state') != 'verified-read-only-first-gib-backup' or
            backup.get('raw_bytes') != SIZE or
            backup.get('phone_writes') is not False or
            backup.get('phone_mounts') is not False or
            sha(V19) != V19_SHA):
        raise ValueError('Root image, backup or V19 recovery image differs')
    chunks = sorted(backup['chunks'], key=lambda item: item['index'])
    if len(chunks) != 8 or [item['index'] for item in chunks] != list(range(8)):
        raise ValueError('First-GiB backup is incomplete')
    for entry in chunks:
        index = entry['index']
        path = Path(entry['path']).resolve(strict=True)
        if (path.parent != BACKUP.parent or
                entry['offset_bytes'] != index * 128 * 1048576 or
                entry['bytes'] != 128 * 1048576 or
                entry['sha256'] != entry['phone_sha256']):
            raise ValueError('Backup chunk location or phone hash differs')
        digest = hashlib.sha256()
        size = 0
        with gzip.open(path, 'rb') as source:
            for block in iter(lambda: source.read(1048576), b''):
                digest.update(block)
                size += len(block)
        if size != entry['bytes'] or digest.hexdigest() != entry['sha256']:
            raise ValueError('Backup chunk data differs: ' + str(index))
    digest = hashlib.sha256()
    size = 0
    with gzip.open(COMPRESSED, 'rb') as source:
        for block in iter(lambda: source.read(1048576), b''):
            digest.update(block)
            size += len(block)
    if size != SIZE or digest.hexdigest() != image['image_sha256']:
        raise ValueError('Compressed root image round trip differs')
    return image, backup


def phone_audit(ip):
    identity = subprocess.run(ssh_command(ip, PROOF), capture_output=True, timeout=15)
    if not proof_valid(identity.stdout.decode(errors='replace'), identity.returncode):
        raise ValueError('Pinned V19 identity refused')
    command = '''set -eu
grep -Fx 'PARTNAME=userdata' /sys/class/block/sdc85/uevent >/dev/null
[ "$(cat /sys/class/block/sdc85/size)" = 466026432 ]
[ -b /dev/sdc85 ]
! grep -Eq '^/dev/sdc85 |^/dev/block/by-name/userdata ' /proc/mounts
grep -Fx 'PARTNAME=boot_a' /sys/class/block/sdc39/uevent >/dev/null
[ "$(cat /sys/class/block/sdc39/size)" = 131072 ]
[ "$(cat /run/lynx/health-bootstrap/ready)" = ready ]
/bin/busybox sh /run/lynx/lynx-health-supervisor.sh --once
for p in /sys/class/power_supply/*; do
    [ -r "$p/online" ] || continue
    [ "$(cat "$p/online")" = 0 ]
done
cat /proc/sys/kernel/random/boot_id
/bin/busybox sha256sum /dev/sdc39'''
    result = subprocess.run(ssh_command(ip, command), capture_output=True, timeout=30)
    if result.returncode:
        raise ValueError('Read-only phone preflight refused: ' +
                         result.stderr.decode(errors='replace')[-300:])
    lines = result.stdout.decode().strip().splitlines()
    if (len(lines) < 3 or not re.fullmatch('[0-9a-f-]{36}', lines[-2]) or
            lines[-1] != V19_SHA + '  /dev/sdc39'):
        raise ValueError('Live boot_a or boot ID differs')
    return lines[-2], lines[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--prepare', action='store_true')
    mode.add_argument('--apply', action='store_true')
    parser.add_argument('--ip', default='192.168.100.4')
    parser.add_argument('--prepared-receipt', type=Path)
    parser.add_argument('--i-accept-overwrite-first-gib', action='store_true')
    args = parser.parse_args()
    if ipaddress.ip_address(args.ip) not in ipaddress.ip_network('192.168.100.0/24'):
        parser.error('IP must be on the isolated Noobia Wi-Fi')
    if args.apply and (args.prepared_receipt is None or
                       not args.i_accept_overwrite_first_gib):
        parser.error('--apply requires a fresh receipt and explicit overwrite flag')
    os.umask(0o077)
    image, backup = local_audit()
    boot_id, health_line = phone_audit(args.ip)
    if boot_id != backup['boot_id']:
        raise ValueError('Backup and current phone boot IDs differ')
    if args.prepare:
        out = ROOT / 'logs' / ('userdata-ext4-prepare-' + str(time.time_ns()))
        out.mkdir(mode=0o700)
        report = {'state': 'prepared-read-only', 'created_ns': time.time_ns(),
                  'phone_ip': args.ip, 'boot_id': boot_id,
                  'current_boot_a_sha256': V19_SHA,
                  'image_sha256': image['image_sha256'],
                  'compressed_image_sha256': image['compressed_sha256'],
                  'backup_receipt': str(BACKUP),
                  'backup_chunk_hashes': [x['sha256'] for x in backup['chunks']],
                  'write_device': '/dev/sdc85', 'write_offset_bytes': 0,
                  'write_bytes': SIZE, 'health_proof': health_line,
                  'phone_writes': False, 'flash_performed': False,
                  'requires_explicit_user_approval': True,
                  'limits': 'Only first GiB backed up; remainder of userdata sampled, not fully backed up. Writing would destroy unidentified data in the first GiB.'}
        (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps({'state': report['state'], 'result': str(out / 'result.json')}))
        return
    prepared_path = args.prepared_receipt.resolve(strict=True)
    if not prepared_path.is_relative_to(ROOT / 'logs'):
        raise ValueError('Prepared receipt outside Lynx logs')
    prepared = json.loads(prepared_path.read_text())
    age_ns = time.time_ns() - prepared.get('created_ns', 0)
    if (prepared.get('state') != 'prepared-read-only' or
            prepared.get('boot_id') != boot_id or
            prepared.get('phone_ip') != args.ip or
            prepared.get('image_sha256') != image['image_sha256'] or
            prepared.get('compressed_image_sha256') != image['compressed_sha256'] or
            prepared.get('backup_receipt') != str(BACKUP) or
            prepared.get('write_bytes') != SIZE or
            age_ns < 0 or age_ns > 15 * 60 * 10**9):
        raise ValueError('Fresh exact prepared receipt required')
    out = ROOT / 'logs' / ('userdata-ext4-install-' + str(time.time_ns()))
    out.mkdir(mode=0o700)
    report = {'state': 'write-not-started', 'created_ns': time.time_ns(),
              'prepared_receipt': str(prepared_path), 'boot_id': boot_id,
              'image_sha256': image['image_sha256'],
              'device': '/dev/sdc85', 'offset_bytes': 0, 'bytes': SIZE,
              'phone_writes': False, 'flash_performed': False}

    def save():
        temp = out / 'result.tmp'
        temp.write_text(json.dumps(report, indent=2) + '\n')
        temp.replace(out / 'result.json')

    save()
    try:
        command = (f'[ "$(cat /proc/sys/kernel/random/boot_id)" = {boot_id} ] && '
                   '/bin/busybox gzip -dc | /bin/busybox dd of=/dev/sdc85 '
                   'bs=1048576 iflag=fullblock count=1024 conv=notrunc,fsync')
        report['state'] = 'write-in-progress'
        report['phone_writes'] = True
        save()
        with COMPRESSED.open('rb') as source:
            written = subprocess.run(ssh_command(args.ip, command), stdin=source,
                                     capture_output=True, timeout=300)
        (out / 'write.stdout').write_bytes(written.stdout)
        (out / 'write.stderr').write_bytes(written.stderr)
        if written.returncode:
            raise ValueError('Install stream failed; first GiB may be partial')
        verify = (f'[ "$(cat /proc/sys/kernel/random/boot_id)" = {boot_id} ] && '
                  '/bin/busybox dd if=/dev/sdc85 bs=1048576 count=1024 '
                  '2>/dev/null | /bin/busybox sha256sum')
        checked = subprocess.run(ssh_command(args.ip, verify),
                                 capture_output=True, timeout=120)
        (out / 'verify.stdout').write_bytes(checked.stdout)
        (out / 'verify.stderr').write_bytes(checked.stderr)
        if checked.returncode or checked.stdout.decode().split()[0] != image['image_sha256']:
            raise ValueError('Installed first GiB hash differs; restore backup')
        mount = '''set -eu
mkdir -p /run/lynx/persistent-root-check
mount -t ext4 -o ro,noload /dev/sdc85 /run/lynx/persistent-root-check
trap 'umount /run/lynx/persistent-root-check || true' EXIT
test "$(cat /run/lynx/persistent-root-check/etc/alpine-release)" = 3.24.2
test -x /run/lynx/persistent-root-check/sbin/openrc-init
umount /run/lynx/persistent-root-check
trap - EXIT
echo EXT4_ALPINE_ROOT_READ_ONLY_VERIFIED'''
        mounted = subprocess.run(ssh_command(args.ip, mount),
                                 capture_output=True, timeout=30)
        (out / 'mount.stdout').write_bytes(mounted.stdout)
        (out / 'mount.stderr').write_bytes(mounted.stderr)
        if mounted.returncode or b'EXT4_ALPINE_ROOT_READ_ONLY_VERIFIED' not in mounted.stdout:
            raise ValueError('Read-only mounted Alpine check failed; inspect before reboot')
        report['state'] = 'ext4-root-installed-and-verified'
    except Exception as error:
        report.update(state='install-failed-or-incomplete', error=str(error))
    report['finished_ns'] = time.time_ns()
    save()
    print(json.dumps({'state': report['state'], 'result': str(out / 'result.json')}))
    if report['state'] != 'ext4-root-installed-and-verified':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
