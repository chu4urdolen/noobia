"""Boot the pinned stock ARM64 kernel with Alpine OpenRC in a RAM-only VM."""
import hashlib
import json
import os
import stat
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'linux-port'))
from image_formats import read_boot_v4, read_newc, require
from prepare_busybox_diagnostics import pack
from ramdisk_codec import decompress

V19_SHA256 = '5ce2dbf8a7c132fa7e31f6be70aa76f83afe8c293e2cd5f02251a532486fd851'
RUNTIME = ROOT / 'linux-port/artifacts/openrc-runtime-root'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    if not (RUNTIME / 'sbin/openrc-init').is_file():
        raise SystemExit('OpenRC runtime root not prepared')
    if (RUNTIME / 'sbin/openrc-init').is_symlink():
        raise SystemExit('Unexpected OpenRC init symlink')
    out = ROOT / 'linux-port/artifacts' / ('openrc-userspace-vm-' + str(time.time_ns()))
    out.mkdir(mode=0o700)
    report = {'state': 'prepared', 'started_ns': time.time_ns(),
              'runtime_root': str(RUNTIME), 'phone_contacted': False,
              'phone_boot_or_partition_changed': False, 'network_enabled': False}

    source = ROOT / 'linux-port/artifacts/busybox-wifi-ssh-twostage-v19/nord3-busybox-candidate.img'
    image = source.read_bytes()
    require(sha(image) == V19_SHA256, 'Frozen stock-kernel boot fixture changed')
    boot = read_boot_v4(image)
    original = read_newc(decompress(boot['ramdisk']))
    entries = {}
    total = 0

    def walk(directory):
        nonlocal total
        for path in sorted(directory.iterdir()):
            name = path.relative_to(RUNTIME).as_posix()
            info = path.lstat()
            mode = info.st_mode
            if stat.S_ISDIR(mode):
                data = b''
                mode = stat.S_IFDIR | stat.S_IMODE(mode)
            elif stat.S_ISREG(mode):
                data = path.read_bytes()
                total += len(data)
                mode = stat.S_IFREG | stat.S_IMODE(mode)
            elif stat.S_ISLNK(mode):
                data = os.readlink(path).encode()
                mode = stat.S_IFLNK | stat.S_IMODE(mode)
            else:
                raise ValueError('Unexpected special file in runtime root: ' + name)
            entries[name] = {'mode': mode, 'uid': 0, 'gid': 0,
                             'rdevmajor': 0, 'rdevminor': 0, 'data': data}
            if stat.S_ISDIR(info.st_mode):
                walk(path)

    walk(RUNTIME)
    require(total <= 128 * 1024 * 1024, 'Runtime root exceeds bounded VM input size')
    for required in ('bin/busybox', 'lib/ld-musl-aarch64.so.1', 'sbin/openrc-init',
                     'sbin/openrc-shutdown', 'sbin/openrc-run', 'etc/inittab'):
        require(required in entries, 'Runtime root lacks ' + required)

    # Reuse the stock image's ARM64 BusyBox and add a tiny deterministic service
    # to prove OpenRC reaches its default runlevel before requesting clean poweroff.
    entries['bin/busybox'] = original['bin/busybox']
    init = b'''#!/bin/busybox sh
set -eu
BB=/bin/busybox
$BB mkdir -p /proc /sys /dev /run
$BB mount -t proc -o nosuid,nodev,noexec proc /proc
$BB mount -t sysfs -o nosuid,nodev,noexec sysfs /sys
$BB mount -t tmpfs -o mode=0755,size=16m tmpfs /dev
$BB mknod -m 600 /dev/console c 5 1
$BB mknod -m 666 /dev/null c 1 3
exec </dev/console >/dev/console 2>&1
$BB mount -t tmpfs -o mode=0755,size=128m tmpfs /run
$BB mkdir -p /etc/runlevels/default
exec /sbin/openrc-init
'''
    service = b'''#!/sbin/openrc-run
description="Lynx OpenRC VM proof"
start() {
    echo LYNX_OPENRC_DEFAULT_RUNLEVEL_PASS > /dev/console
    ( /bin/busybox sleep 2; echo LYNX_OPENRC_SHUTDOWN_REQUEST > /dev/console; /sbin/openrc-shutdown --poweroff now ) </dev/null >/dev/console 2>&1 &
    return 0
}
'''
    entries['init'] = {'mode': stat.S_IFREG | 0o755, 'uid': 0, 'gid': 0,
                       'rdevmajor': 0, 'rdevminor': 0, 'data': init}
    entries['etc/init.d/lynx-vm-proof'] = {
        'mode': stat.S_IFREG | 0o755, 'uid': 0, 'gid': 0,
        'rdevmajor': 0, 'rdevminor': 0, 'data': service}
    entries['etc/runlevels/default/lynx-vm-proof'] = {
        'mode': stat.S_IFLNK | 0o777, 'uid': 0, 'gid': 0,
        'rdevmajor': 0, 'rdevminor': 0, 'data': b'../../init.d/lynx-vm-proof'}
    for name, major, minor, mode in [('dev/console', 5, 1, 0o600), ('dev/null', 1, 3, 0o666)]:
        entries[name] = {'mode': stat.S_IFCHR | mode, 'uid': 0, 'gid': 0,
                         'rdevmajor': major, 'rdevminor': minor, 'data': b''}
    ordered = dict(sorted(entries.items(), key=lambda pair: (
        not stat.S_ISDIR(pair[1]['mode']), pair[0].count('/'), pair[0])))
    ramdisk = pack(ordered)
    (out / 'init-source').write_bytes(init)
    (out / 'openrc-service').write_bytes(service)
    (out / 'Image').write_bytes(__import__('gzip').decompress(boot['kernel']))
    (out / 'initramfs.cpio.lz4').write_bytes(ramdisk)

    q = ROOT / 'tools/qemu/noble/root'
    command = [str(q / 'usr/bin/qemu-system-aarch64'), '-L', str(q / 'usr/share/qemu'),
               '-no-user-config', '-nodefaults', '-machine', 'virt,gic-version=3', '-accel', 'tcg',
               '-cpu', 'cortex-a710', '-smp', '2', '-m', '1024', '-display', 'none', '-monitor', 'none',
               '-serial', 'stdio', '-nic', 'none', '-no-reboot', '-kernel', str(out / 'Image'),
               '-initrd', str(out / 'initramfs.cpio.lz4'),
               '-append', 'console=ttyAMA0 rdinit=/init loglevel=7 panic=0']
    env = dict(os.environ, LD_LIBRARY_PATH=str(q / 'usr/lib/x86_64-linux-gnu'),
               QEMU_MODULE_DIR=str(q / 'usr/lib/x86_64-linux-gnu/qemu'), TMPDIR=str(out))
    report.update(command=command, kernel_sha256=sha(boot['kernel']),
                  initramfs_bytes=len(ramdisk), rootfs_regular_bytes=total)
    started = time.monotonic()
    with (out / 'console.log').open('wb') as console:
        try:
            proc = subprocess.run(command, env=env, stdout=console,
                                  stderr=subprocess.STDOUT, timeout=30)
            rc, timed_out = proc.returncode, False
        except subprocess.TimeoutExpired:
            rc, timed_out = None, True
    output = (out / 'console.log').read_bytes()
    checks = {
        'openrc_init_pid1_started': b'OpenRC init version 0.63.2 starting' in output,
        'default_runlevel_service_ran': b'LYNX_OPENRC_DEFAULT_RUNLEVEL_PASS' in output,
        'clean_poweroff': b'reboot: Power down' in output,
        'no_kernel_panic': b'Kernel panic' not in output,
    }
    passed = rc == 0 and not timed_out and all(checks.values())
    report.update(state='openrc-userspace-verified' if passed else 'failed', checks=checks,
                  console_sha256=sha(output), exit_code=rc, timed_out=timed_out,
                  elapsed_seconds=time.monotonic() - started, finished_ns=time.time_ns(),
                  limits='OpenRC Alpine userspace booted under QEMU with the frozen stock kernel; no phone access, networking, flashing, or persistent install.')
    (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'state': report['state'], 'result': str(out / 'result.json')}))
    if not passed:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
