"""Resumable read-only first-GiB backup in eight verified 128 MiB chunks."""
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
BLOCK = 1 << 20
CHUNK_BLOCKS = 128
CHUNKS = 8
PARTIAL = ROOT / 'backups/userdata-first-gib-1792413857581940907/userdata-first-gib.img.gz'
EDGE = ROOT / 'backups/userdata-edges-1792413021056852842/result.json'


def save(path, data):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, indent=2) + '\n')
    tmp.replace(path)


def local_hash(path, *, first=False):
    digest = hashlib.sha256()
    leading = hashlib.sha256()
    total = 0
    with gzip.open(path, 'rb') as source:
        for block in iter(lambda: source.read(BLOCK), b''):
            digest.update(block)
            if first and total < 16 * BLOCK:
                leading.update(block[:16 * BLOCK - total])
            total += len(block)
    if total != CHUNK_BLOCKS * BLOCK:
        raise ValueError('Chunk is incomplete: ' + str(path))
    return digest.hexdigest(), leading.hexdigest() if first else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ip', default='192.168.100.4')
    parser.add_argument('--resume', type=Path)
    args = parser.parse_args()
    if ipaddress.ip_address(args.ip) not in ipaddress.ip_network('192.168.100.0/24'):
        parser.error('IP must be on the isolated Noobia Wi-Fi')
    os.umask(0o077)
    if args.resume:
        out = args.resume.resolve(strict=True)
        if not out.is_relative_to(ROOT / 'backups') or not out.name.startswith('userdata-chunks-'):
            parser.error('Resume directory must be a Lynx userdata-chunks backup')
        report = json.loads((out / 'result.json').read_text())
        if report.get('state') == 'verified-read-only-first-gib-backup':
            print(json.dumps({'state': report['state'], 'result': str(out / 'result.json')}))
            return
    else:
        out = ROOT / 'backups' / ('userdata-chunks-' + str(time.time_ns()))
        out.mkdir(parents=True, mode=0o700)
        report = {'state': 'starting', 'created_ns': time.time_ns(),
                  'device': '/dev/sdc85', 'offset_bytes': 0,
                  'raw_bytes': CHUNKS * CHUNK_BLOCKS * BLOCK,
                  'phone_writes': False, 'phone_mounts': False,
                  'source_partial': str(PARTIAL), 'chunks': []}
    receipt = out / 'result.json'
    save(receipt, report)
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
        checked = subprocess.run(ssh_command(args.ip, preflight),
                                 capture_output=True, timeout=15)
        if checked.returncode:
            raise ValueError('Partition or health preflight refused')
        boot_id = checked.stdout.decode().strip().splitlines()[-1]
        if report.get('boot_id') not in (None, boot_id):
            raise ValueError('Resume boot ID changed; inspect before continuing')
        report['boot_id'] = boot_id
        save(receipt, report)
        edge = json.loads(EDGE.read_text())
        first_sha = next(part['sha256'] for part in edge['parts']
                         if part['name'] == 'head')
        existing = {entry['index']: entry for entry in report['chunks']}

        def phone_hash(index):
            skip = index * CHUNK_BLOCKS
            command = (f'[ "$(cat /proc/sys/kernel/random/boot_id)" = {boot_id} ] && '
                       f'/bin/busybox dd if=/dev/sdc85 bs={BLOCK} '
                       f'skip={skip} count={CHUNK_BLOCKS} 2>/dev/null | '
                       '/bin/busybox sha256sum')
            result = subprocess.run(ssh_command(args.ip, command),
                                    capture_output=True, timeout=120)
            digest = result.stdout.decode(errors='replace').split()[0] if result.stdout else ''
            if result.returncode or not re.fullmatch('[0-9a-f]{64}', digest):
                raise ValueError('Phone chunk hash refused: ' + str(index))
            return digest

        partial_stream = gzip.open(PARTIAL, 'rb') if not args.resume else None
        try:
            for index in range(CHUNKS):
                path = out / f'chunk-{index:02d}.img.gz'
                if path.exists():
                    local, leading = local_hash(path, first=index == 0)
                elif index < 4 and partial_stream is not None:
                    with path.open('wb') as file:
                        with gzip.GzipFile(filename='', mode='wb', fileobj=file,
                                           compresslevel=1, mtime=0) as target:
                            for _ in range(CHUNK_BLOCKS):
                                block = partial_stream.read(BLOCK)
                                if len(block) != BLOCK:
                                    raise ValueError('Truncated source before salvaged chunk')
                                target.write(block)
                    local, leading = local_hash(path, first=index == 0)
                else:
                    skip = index * CHUNK_BLOCKS
                    command = (f'[ "$(cat /proc/sys/kernel/random/boot_id)" = {boot_id} ] && '
                               f'/bin/busybox dd if=/dev/sdc85 bs={BLOCK} '
                               f'skip={skip} count={CHUNK_BLOCKS} 2>/dev/null | '
                               '/bin/busybox gzip -1')
                    temporary = out / f'chunk-{index:02d}.partial'
                    with temporary.open('wb') as file:
                        copied = subprocess.run(ssh_command(args.ip, command),
                                                stdout=file, stderr=subprocess.PIPE,
                                                timeout=300)
                    (out / f'chunk-{index:02d}.stderr').write_bytes(copied.stderr)
                    if copied.returncode:
                        raise ValueError('Chunk transfer failed: ' + str(index))
                    temporary.replace(path)
                    local, leading = local_hash(path, first=index == 0)
                if index == 0 and leading != first_sha:
                    raise ValueError('First chunk disagrees with earlier edge backup')
                remote = phone_hash(index)
                if local != remote:
                    raise ValueError('Phone and host chunk hashes differ: ' + str(index))
                record = {'index': index, 'offset_bytes': index * CHUNK_BLOCKS * BLOCK,
                          'bytes': CHUNK_BLOCKS * BLOCK,
                          'compressed_bytes': path.stat().st_size,
                          'sha256': local, 'phone_sha256': remote,
                          'path': str(path)}
                if index in existing:
                    if existing[index] != record:
                        raise ValueError('Resume manifest chunk differs: ' + str(index))
                else:
                    report['chunks'].append(record)
                    existing[index] = record
                report['state'] = 'partial-verified'
                save(receipt, report)
        finally:
            if partial_stream is not None:
                partial_stream.close()
        if len(report['chunks']) != CHUNKS:
            raise ValueError('Backup chunk set incomplete')
        report['state'] = 'verified-read-only-first-gib-backup'
    except Exception as error:
        report.update(state='failed', error=str(error))
    report['finished_ns'] = time.time_ns()
    save(receipt, report)
    print(json.dumps({'state': report['state'], 'result': str(receipt)}))
    if report['state'] != 'verified-read-only-first-gib-backup':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
