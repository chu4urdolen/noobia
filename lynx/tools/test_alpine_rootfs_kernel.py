"""Execute the verified Alpine userspace in a NIC-free exact-stock-kernel VM."""
import argparse
import gzip
import hashlib
import json
import os
import subprocess
import tarfile
import time
from pathlib import Path, PurePosixPath

from alpine_rootfs import ROOT, PROBE, read_rootfs
from image_formats import read_boot_v4, read_newc
from ramdisk_codec import decompress
from prepare_busybox_diagnostics import pack
from network_userspace import put


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--rootfs-receipt', type=Path, required=True)
    parser.add_argument('--apk-cache-receipt', type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    rootfs, inventory = read_rootfs(args.rootfs_receipt)
    port = ROOT / 'linux-port'
    raw = (port / 'artifacts/busybox-wifi-ssh-twostage-v19/nord3-busybox-candidate.img').read_bytes()
    if hashlib.sha256(raw).hexdigest() != '5ce2dbf8a7c132fa7e31f6be70aa76f83afe8c293e2cd5f02251a532486fd851':
        raise ValueError('V19 reference changed')
    boot = read_boot_v4(raw)
    known = read_newc(decompress(boot['ramdisk']))
    entries = {}
    put(entries, 'bin/busybox', known['bin/busybox']['data'])
    put(entries, 'rootfs', b'', 0o40755)
    for name, item in rootfs.items():
        entries['rootfs/' + name] = item
    put(entries, 'rootfs/lynx-userspace-probe.sh', PROBE.encode(), 0o100600)
    offline_packages = []
    if args.apk_cache_receipt:
        capture = json.loads(args.apk_cache_receipt.read_text())
        operation = next(op for op in capture['operations'] if op['name'] == 'command')
        cache = args.apk_cache_receipt.with_name('command.stdout')
        if not capture.get('native_identity_verified') or operation['exit_code'] != 0 or hashlib.sha256(cache.read_bytes()).hexdigest() != operation['stdout_sha256']:
            raise ValueError('Verified APK cache capture required')
        selected = {'libbz2-1.0.8-r6.apk', 'libdw-0.195-r0.apk', 'libelf-0.195-r0.apk',
                    'musl-fts-1.2.7-r7.apk', 'strace-6.19-r1.apk', 'xz-libs-5.8.4-r0.apk', 'zstd-libs-1.5.7-r2.apk'}
        with tarfile.open(cache, 'r:gz') as archive:
            for member in archive:
                path = PurePosixPath(member.name)
                if path.is_absolute() or '..' in path.parts:
                    raise ValueError('Unsafe cache archive path')
                if not member.isfile() or path.name not in selected:
                    continue
                if member.size > 16 * 1024 * 1024 or any(item['name'] == path.name for item in offline_packages):
                    raise ValueError('Oversized/duplicate cached package')
                data = archive.extractfile(member).read()
                put(entries, 'rootfs/tmp/lynx-offline-apks/' + path.name, data, 0o100600)
                offline_packages.append({'name': path.name, 'sha256': hashlib.sha256(data).hexdigest()})
        if {item['name'] for item in offline_packages} != selected:
            raise ValueError('Incomplete exact diagnostic package set')
        put(entries, 'rootfs/lynx-offline-probe.sh', b'''set -eu
if /sbin/apk info -e strace; then exit 1; fi
/sbin/apk --no-network --repositories-file /dev/null --cache-dir /tmp/lynx-offline-apks --cache-packages add /tmp/lynx-offline-apks/*.apk
/usr/bin/strace -f -o /tmp/strace.log /bin/true
test -s /tmp/strace.log
grep 'exited with 0' /tmp/strace.log
echo LYNX_ALPINE_OFFLINE_DIAGNOSTICS_PASS
''', 0o100600)
    init = b'''#!/bin/busybox sh
BB=/bin/busybox
$BB mkdir -p /proc /sys /dev
$BB mount -t proc proc /proc
$BB mount -t sysfs sysfs /sys
$BB mount -t tmpfs tmpfs /dev
$BB mknod -m 600 /dev/console c 5 1
$BB mknod -m 666 /dev/null c 1 3
exec </dev/console >/dev/console 2>&1
$BB chroot /rootfs /bin/sh /lynx-userspace-probe.sh
rc=$?
echo LYNX_ALPINE_VM_CHROOT_EXIT=$rc
$BB poweroff -f
'''
    if offline_packages:
        init = init.replace(b'$BB poweroff -f', b'''$BB mknod -m 666 /rootfs/dev/null c 1 3
$BB chroot /rootfs /bin/sh /lynx-offline-probe.sh
echo LYNX_ALPINE_VM_OFFLINE_EXIT=$?
$BB poweroff -f''')
    put(entries, 'init', init)
    out = port / 'artifacts' / ('emulated-alpine-rootfs-' + str(time.time_ns()))
    out.mkdir(mode=0o700)
    (out / 'Image').write_bytes(gzip.decompress(boot['kernel']))
    (out / 'initramfs').write_bytes(pack(entries))
    (out / 'init-source').write_bytes(init)
    (out / 'inventory.json').write_text(json.dumps(inventory, indent=2) + '\n')
    q = ROOT / 'tools/qemu/noble/root'
    command = [str(q / 'usr/bin/qemu-system-aarch64'), '-L', str(q / 'usr/share/qemu'),
               '-no-user-config', '-nodefaults', '-machine', 'virt,gic-version=3', '-accel', 'tcg',
               '-cpu', 'cortex-a710', '-smp', '2', '-m', '1024', '-display', 'none', '-monitor', 'none',
               '-serial', 'stdio', '-nic', 'none', '-no-reboot', '-kernel', str(out / 'Image'),
               '-initrd', str(out / 'initramfs'), '-append', 'console=ttyAMA0 rdinit=/init loglevel=7 panic=0']
    environment = dict(os.environ, LD_LIBRARY_PATH=str(q / 'usr/lib/x86_64-linux-gnu'),
                       QEMU_MODULE_DIR=str(q / 'usr/lib/x86_64-linux-gnu/qemu'), TMPDIR=str(out))
    started = time.monotonic()
    try:
        process = subprocess.run(command, env=environment, capture_output=True, timeout=55)
        raw, rc, timed_out = process.stdout + process.stderr, process.returncode, False
    except subprocess.TimeoutExpired as error:
        raw, rc, timed_out = (error.stdout or b'') + (error.stderr or b''), None, True
    (out / 'console.log').write_bytes(raw)
    checks = {'probe_passed': b'LYNX_ALPINE_USERSPACE_PASS' in raw,
              'chroot_exit_zero': b'LYNX_ALPINE_VM_CHROOT_EXIT=0' in raw,
              'matching_kernel': b'5.10.149-android12-9-o-g311738fbb5a8' in raw,
              'clean_poweroff': b'reboot: Power down' in raw,
              'no_kernel_panic': b'Kernel panic' not in raw}
    if offline_packages:
        checks.update(offline_install_and_trace=b'LYNX_ALPINE_OFFLINE_DIAGNOSTICS_PASS' in raw,
                      offline_exit_zero=b'LYNX_ALPINE_VM_OFFLINE_EXIT=0' in raw)
    report = {'passed': rc == 0 and not timed_out and all(checks.values()), 'checks': checks,
              'inventory': inventory, 'rootfs_receipt': str(args.rootfs_receipt.resolve()),
              'kernel_sha256': hashlib.sha256(boot['kernel']).hexdigest(),
              'exit_code': rc, 'timed_out': timed_out, 'elapsed_seconds': time.monotonic() - started,
              'console_sha256': hashlib.sha256(raw).hexdigest(), 'command': command,
              'offline_packages': offline_packages,
              'phone_contacted': False, 'network_enabled': False,
              'limits': 'Shell, musl and APK execution in chroot on exact stock kernel. No handset or package download test.'}
    (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'passed': report['passed'], 'result': str(out / 'result.json')}))
    if not report['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
