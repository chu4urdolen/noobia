"""Boot the stock kernel in QEMU and verify a saved Alpine userspace snapshot."""
import argparse
import hashlib
import json
import os
import stat
import subprocess
import sys
import tarfile
import time
from pathlib import Path, PurePosixPath

from alpine_rootfs import ROOT
sys.path.insert(0, str(ROOT / 'linux-port'))
from image_formats import read_boot_v4, read_newc
from prepare_busybox_diagnostics import pack
from ramdisk_codec import decompress

V19_SHA256 = '5ce2dbf8a7c132fa7e31f6be70aa76f83afe8c293e2cd5f02251a532486fd851'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def load_snapshot(receipt_path):
    receipt = json.loads(receipt_path.read_text())
    if receipt.get('state') != 'checkpoint-verified' or receipt.get('restoration_tested'):
        raise ValueError('Expected a verified checkpoint that still needs a restore test')
    archive_path = Path(receipt['archive']).resolve(strict=True)
    archive = archive_path.read_bytes()
    if len(archive) != receipt['archive_bytes'] or sha(archive) != receipt['archive_sha256']:
        raise ValueError('Checkpoint archive hash/size mismatch')
    inventory = (receipt_path.parent / 'packages-and-world.txt').read_bytes()
    marker = b'LYNX_APK_WORLD\n'
    if inventory.count(marker) != 1:
        raise ValueError('Missing package/world inventory separator')
    packages, world = inventory.split(marker)
    if not packages.endswith(b'\n') or not world.endswith(b'\n'):
        raise ValueError('Incomplete package/world inventory')

    entries = {}
    total = 0
    with tarfile.open(archive_path, 'r:gz') as source:
        for member in source:
            path = PurePosixPath(member.name)
            if path.is_absolute() or '..' in path.parts:
                raise ValueError('Unsafe checkpoint path')
            name = str(path)
            if name == '.':
                continue
            name = name.removeprefix('./')
            if not name or name in entries or len(entries) >= 50000:
                raise ValueError('Empty, duplicate, or excessive checkpoint path')
            if path.parts[0] in {'proc', 'sys', 'dev'}:
                raise ValueError('Checkpoint contains kernel/device mount tree')
            if member.isfile():
                data = source.extractfile(member).read()
                total += len(data)
                if len(data) != member.size or total > 512 * 1024 * 1024:
                    raise ValueError('Truncated or excessive regular file')
                mode = stat.S_IFREG | (member.mode & 0o7777)
            elif member.isdir():
                data, mode = b'', stat.S_IFDIR | (member.mode & 0o7777)
            elif member.issym():
                data, mode = member.linkname.encode(), stat.S_IFLNK | (member.mode & 0o7777)
            else:
                raise ValueError('Special files and hard links are not accepted')
            entries['rootfs/' + name] = {'mode': mode, 'uid': member.uid, 'gid': member.gid,
                                         'rdevmajor': 0, 'rdevminor': 0, 'data': data}

    # Validate lexical parents before cpio construction. Chroot keeps absolute
    # symlinks within the restored tree; no host extraction is performed.
    names = {name.removeprefix('rootfs/'): item for name, item in entries.items()}
    for name in names:
        for parent in PurePosixPath(name).parents:
            if str(parent) == '.':
                continue
            item = names.get(str(parent))
            if item and not stat.S_ISDIR(item['mode']):
                raise ValueError('Checkpoint member below non-directory parent')
    if total != receipt['regular_file_bytes'] or len(entries) != receipt['entries']:
        raise ValueError('Checkpoint content inventory differs from receipt')
    required = ['rootfs/bin/busybox', 'rootfs/sbin/apk', 'rootfs/etc/alpine-release',
                'rootfs/etc/apk/world']
    if any(name not in entries for name in required):
        raise ValueError('Snapshot lacks required Alpine rootfs files')
    development_tools = all('rootfs/' + path in entries for path in
                            ['usr/bin/python3', 'usr/bin/git', 'usr/bin/make'])
    entries['expected-packages'] = {'mode': stat.S_IFREG | 0o600, 'uid': 0, 'gid': 0,
                                    'rdevmajor': 0, 'rdevminor': 0, 'data': packages}
    entries['expected-world'] = {'mode': stat.S_IFREG | 0o600, 'uid': 0, 'gid': 0,
                                 'rdevmajor': 0, 'rdevminor': 0, 'data': world}
    return receipt, entries, development_tools


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkpoint', type=Path, required=True)
    args = parser.parse_args()
    receipt, entries, development_tools = load_snapshot(args.checkpoint.resolve(strict=True))
    out = ROOT / 'linux-port/artifacts' / ('alpine-checkpoint-restore-' + str(time.time_ns()))
    out.mkdir(mode=0o700)
    report = {'state': 'prepared', 'checkpoint': str(args.checkpoint.resolve()),
              'checkpoint_sha256': receipt['archive_sha256'], 'started_ns': time.time_ns(),
              'host_extraction_performed': False, 'phone_contacted': False,
              'phone_boot_or_partition_changed': False}

    boot_path = ROOT / 'linux-port/artifacts/busybox-wifi-ssh-twostage-v19/nord3-busybox-candidate.img'
    boot_bytes = boot_path.read_bytes()
    if sha(boot_bytes) != V19_SHA256:
        raise ValueError('Frozen V19 kernel image changed')
    boot = read_boot_v4(boot_bytes)
    original = read_newc(decompress(boot['ramdisk']))
    entries['rootfs'] = {'mode': stat.S_IFDIR | 0o755, 'uid': 0, 'gid': 0,
                         'rdevmajor': 0, 'rdevminor': 0, 'data': b''}
    from network_userspace import put
    put(entries, 'bin/busybox', original['bin/busybox']['data'], original['bin/busybox']['mode'])
    for applet in ['sh', 'cat', 'cmp', 'mkdir', 'mount', 'mknod', 'sha256sum', 'chroot', 'uname']:
        put(entries, 'bin/' + applet, b'busybox', stat.S_IFLNK | 0o777)
    init = b'''#!/bin/busybox sh
set -eu
BB=/bin/busybox
$BB mkdir -p /proc /sys /dev /rootfs/proc /rootfs/sys /rootfs/dev /tmp
$BB mount -t proc proc /proc
$BB mount -t sysfs sysfs /sys
$BB mount -t tmpfs tmpfs /dev
$BB mknod -m 600 /dev/console c 5 1
$BB mknod -m 666 /dev/null c 1 3
exec </dev/console >/dev/console 2>&1
$BB mount -t proc -o ro,nosuid,nodev,noexec proc /rootfs/proc
$BB mount -t sysfs -o ro,nosuid,nodev,noexec sysfs /rootfs/sys
$BB mount -t tmpfs -o size=8m tmpfs /rootfs/dev
$BB mknod -m 600 /rootfs/dev/console c 5 1
$BB mknod -m 666 /rootfs/dev/null c 1 3
test "$(cat /rootfs/etc/alpine-release)" = 3.24.2
sha256sum /rootfs/etc/apk/world
$BB chroot /rootfs /sbin/apk info -v > /tmp/packages
$BB cmp /tmp/packages /expected-packages
$BB cmp /rootfs/etc/apk/world /expected-world
echo LYNX_CHECKPOINT_PACKAGE_STATE_PASS
$BB poweroff -f
'''
    if development_tools:
        development = b'''$BB chroot /rootfs /usr/bin/python3 -c 'import hashlib,json,platform,sqlite3,ssl,threading; assert platform.machine()=="aarch64"; c=sqlite3.connect(":memory:"); assert c.execute("select 6*7").fetchone()[0]==42; t=threading.Thread(target=lambda: hashlib.sha256(b"lynx").hexdigest()); t.start(); t.join(); print(json.dumps({"python":platform.python_version(),"sqlite":sqlite3.sqlite_version,"ssl":ssl.OPENSSL_VERSION,"stdlib":"pass"}))'
$BB chroot /rootfs /usr/bin/git --version
$BB chroot /rootfs /usr/bin/make --version
$BB mkdir -p /rootfs/tmp/lynx-build-check
printf 'answer:\n\tprintf "42\\n" > answer\n' > /rootfs/tmp/lynx-build-check/Makefile
$BB chroot /rootfs /usr/bin/make -C /tmp/lynx-build-check
test "$(cat /rootfs/tmp/lynx-build-check/answer)" = 42
echo LYNX_CHECKPOINT_PYTHON_GIT_MAKE_PASS
'''
        init = init.replace(b'$BB poweroff -f', development + b'$BB poweroff -f')
    entries['init'] = {'mode': stat.S_IFREG | 0o755, 'uid': 0, 'gid': 0,
                       'rdevmajor': 0, 'rdevminor': 0, 'data': init}
    ordered = dict(sorted(entries.items(), key=lambda pair: (
        not stat.S_ISDIR(pair[1]['mode']), pair[0].count('/'), pair[0])))
    ramdisk = pack(ordered)
    kernel = out / 'Image'; kernel.write_bytes(__import__('gzip').decompress(boot['kernel']))
    initrd = out / 'initramfs.cpio.lz4'; initrd.write_bytes(ramdisk)
    (out / 'init-source').write_bytes(init)
    q = ROOT / 'tools/qemu/noble/root'
    command = [str(q / 'usr/bin/qemu-system-aarch64'), '-L', str(q / 'usr/share/qemu'),
               '-no-user-config', '-nodefaults', '-machine', 'virt,gic-version=3', '-accel', 'tcg',
               '-cpu', 'cortex-a710', '-smp', '2', '-m', '1024', '-display', 'none', '-monitor', 'none',
               '-serial', 'stdio', '-nic', 'none', '-no-reboot', '-kernel', str(kernel), '-initrd', str(initrd),
               '-append', 'console=ttyAMA0 rdinit=/init loglevel=7 panic=0']
    report.update(command=command, ramdisk_bytes=len(ramdisk), kernel_sha256=sha(boot['kernel']))
    env = dict(os.environ, LD_LIBRARY_PATH=str(q / 'usr/lib/x86_64-linux-gnu'),
               QEMU_MODULE_DIR=str(q / 'usr/lib/x86_64-linux-gnu/qemu'), TMPDIR=str(out))
    started = time.monotonic()
    with (out / 'console.log').open('wb') as console:
        try:
            process = subprocess.run(command, env=env, stdout=console, stderr=subprocess.STDOUT, timeout=55)
            rc, timed_out = process.returncode, False
        except subprocess.TimeoutExpired:
            rc, timed_out = None, True
    data = (out / 'console.log').read_bytes()
    checks = {'package_world_match': b'LYNX_CHECKPOINT_PACKAGE_STATE_PASS\r\n' in data,
              'clean_poweroff': b'reboot: Power down' in data,
              'no_kernel_panic': b'Kernel panic' not in data}
    if development_tools:
        checks['python_git_make_run'] = b'LYNX_CHECKPOINT_PYTHON_GIT_MAKE_PASS\r\n' in data
    passed = rc == 0 and not timed_out and all(checks.values())
    report.update(state='restoration-verified' if passed else 'failed', checks=checks,
                  console_sha256=sha(data), exit_code=rc, timed_out=timed_out,
                  elapsed_seconds=time.monotonic() - started, finished_ns=time.time_ns(),
                  development_tools_present=development_tools,
                  limits='Restored checkpoint tested in QEMU with the stock kernel and no network/device access; not a phone boot or persistent phone installation.')
    (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'state': report['state'], 'result': str(out / 'result.json')}))
    if not passed:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
