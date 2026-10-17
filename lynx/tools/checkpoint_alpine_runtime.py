"""Capture the RAM chroot to a private host archive, excluding kernel mounts."""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import tarfile
import time
import uuid
from pathlib import Path, PurePosixPath

from alpine_rootfs import ROOT, ARCHIVE_SHA256
from fetch_alpine_rootfs import VERSION


def inspect_archive(path):
    records, names, total = [], set(), 0
    with tarfile.open(path, 'r:gz') as source:
        for member in source:
            name = str(PurePosixPath(member.name))
            if name == '.':
                continue
            if PurePosixPath(name).is_absolute() or '..' in PurePosixPath(name).parts or name in names:
                raise ValueError('Unsafe or duplicate snapshot member')
            if PurePosixPath(name).parts[0] in {'proc', 'sys', 'dev'}:
                raise ValueError('Kernel/device tree unexpectedly included')
            if len(records) >= 50000 or member.size > 64 * 1024 * 1024:
                raise ValueError('Snapshot size/count cap exceeded')
            record = {'path': name, 'mode': member.mode, 'uid': member.uid, 'gid': member.gid}
            if member.isfile():
                data = source.extractfile(member).read()
                total += len(data)
                if len(data) != member.size or total > 512 * 1024 * 1024:
                    raise ValueError('Truncated or excessive snapshot content')
                record.update(kind='file', bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
            elif member.isdir():
                record['kind'] = 'directory'
            elif member.issym():
                record.update(kind='symlink', target=member.linkname)
            elif member.islnk() and not PurePosixPath(member.linkname).is_absolute() and '..' not in PurePosixPath(member.linkname).parts:
                record.update(kind='hardlink', target=member.linkname)
            else:
                raise ValueError('Unexpected special snapshot member')
            names.add(name); records.append(record)
    if not {'bin/busybox', 'sbin/apk', 'etc/alpine-release', 'etc/apk/world'} <= names:
        raise ValueError('Incomplete userspace snapshot')
    return {'entries': len(records), 'regular_file_bytes': total, 'members': records,
            'host_extraction_performed': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--session', type=Path)
    parser.add_argument('--rootfs-trial', type=Path)
    parser.add_argument('--capture', action='store_true')
    args = parser.parse_args()
    if not args.capture:
        print('Use --session RECEIPT --rootfs-trial RECEIPT --capture. No phone contacted.')
        return
    if args.session is None or args.rootfs_trial is None:
        parser.error('--session and --rootfs-trial required')
    args.session = args.session.resolve(strict=True)
    trial = json.loads(args.rootfs_trial.read_text())
    root = '/run/lynx/alpine-' + VERSION
    if not (trial.get('native_rootfs_verified') and trial.get('original_runtime_verified')
            and trial.get('rootfs_left_in_ram') and Path(trial['session']).resolve() == args.session
            and trial['destination'] == root and trial['rootfs_inventory']['archive_sha256'] == ARCHIVE_SHA256):
        raise ValueError('Matching verified continuous RAM rootfs receipt required')
    boot_id = str(uuid.UUID(trial['boot_id']))
    os.umask(0o077)
    out = ROOT / 'checkpoints' / ('alpine-runtime-' + str(time.time_ns()))
    out.mkdir(mode=0o700)
    report = {'state': 'capturing', 'started_ns': time.time_ns(), 'session': str(args.session),
              'rootfs_trial': str(args.rootfs_trial.resolve()), 'boot_id': boot_id, 'operations': [],
              'partition_writes': False, 'phone_shutdown': False, 'host_extraction_performed': False}
    def save():
        (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    def live(name, command):
        op = {'name': name, 'started_ns': time.time_ns()}; report['operations'].append(op); save()
        with (out / (name + '.stdout')).open('wb') as stdout, (out / (name + '.stderr')).open('wb') as stderr:
            result = subprocess.run([sys.executable, str(ROOT / 'tools/lynx_live_command.py'), '--session', str(args.session),
                                     '--name', 'alpine-checkpoint-' + name, '--timeout', '55', '--command', command],
                                    stdout=stdout, stderr=stderr, timeout=120)
        op.update(exit_code=result.returncode, finished_ns=time.time_ns()); save()
        if result.returncode:
            raise ValueError(name + ' failed; raw capture retained')
        metadata = json.loads((out / (name + '.stdout')).read_bytes())
        receipt_path = Path(metadata['result'])
        receipt = json.loads(receipt_path.read_text())
        command_op = next(item for item in receipt['operations'] if item['name'] == 'command')
        raw = receipt_path.with_name('command.stdout').read_bytes()
        if not receipt.get('native_identity_verified') or command_op['exit_code'] != 0 or hashlib.sha256(raw).hexdigest() != command_op['stdout_sha256']:
            raise ValueError('Native capture proof/hash mismatch')
        op['capture_receipt'] = str(receipt_path); save()
        return raw
    guard = 'set -eu; test "$(cat /proc/sys/kernel/random/boot_id)" = ' + boot_id + '; test "$(cat ' + root + '/etc/alpine-release)" = ' + VERSION + '; '
    inventory = guard + '/bin/busybox chroot ' + root + ' /sbin/apk info -v; echo LYNX_APK_WORLD; cat ' + root + '/etc/apk/world'
    try:
        before = live('inventory-before', inventory)
        archive = live('archive', guard + '/bin/busybox tar -czf - --exclude=./proc --exclude=./sys --exclude=./dev -C ' + root + ' .')
        after = live('inventory-after', inventory)
        if before != after:
            raise ValueError('Package/world state changed during capture; not a consistent package checkpoint')
        path = out / 'rootfs.tar.gz'
        path.write_bytes(archive)
        inspection = inspect_archive(path)
        (out / 'inventory.json').write_text(json.dumps(inspection, indent=2) + '\n')
        (out / 'packages-and-world.txt').write_bytes(before)
        report.update(state='checkpoint-verified', archive=str(path), archive_sha256=hashlib.sha256(archive).hexdigest(),
                      archive_bytes=len(archive), entries=inspection['entries'], regular_file_bytes=inspection['regular_file_bytes'],
                      package_inventory_stable=True, restoration_tested=False,
                      limits='Private userspace archive with stable APK/world inventory; not an atomic filesystem snapshot or a boot image.')
    except Exception as error:
        report.update(state='failed', error=str(error))
    report['finished_ns'] = time.time_ns(); save()
    print(json.dumps({'state': report['state'], 'result': str(out / 'result.json')}))
    if report['state'] != 'checkpoint-verified':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
