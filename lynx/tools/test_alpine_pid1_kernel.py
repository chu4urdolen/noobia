"""Boot Alpine itself as PID 1 in a NIC-free VM; never contacts the phone."""
import argparse
import gzip
import hashlib
import json
import os
import subprocess
import time
from pathlib import Path

from alpine_rootfs import ROOT, PROBE, read_rootfs
from image_formats import read_boot_v4
from network_userspace import put
from prepare_busybox_diagnostics import pack


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rootfs-receipt', type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    entries, inventory = read_rootfs(args.rootfs_receipt)
    reference = ROOT / 'linux-port/artifacts/busybox-wifi-ssh-twostage-v19/nord3-busybox-candidate.img'
    raw = reference.read_bytes()
    if hashlib.sha256(raw).hexdigest() != '5ce2dbf8a7c132fa7e31f6be70aa76f83afe8c293e2cd5f02251a532486fd851':
        raise ValueError('V19 kernel reference changed')
    boot = read_boot_v4(raw)
    alpine_busybox_hash = hashlib.sha256(entries['bin/busybox']['data']).hexdigest()
    init = '''#!/bin/sh
set -eu
mkdir -p /proc /sys /dev /run
mount -t proc proc /proc
mount -t sysfs sysfs /sys
mount -t tmpfs -o mode=0755 tmpfs /dev
mknod -m 600 /dev/console c 5 1
mknod -m 666 /dev/null c 1 3
mknod -m 666 /dev/zero c 1 5
mknod -m 666 /dev/random c 1 8
mknod -m 666 /dev/urandom c 1 9
exec </dev/console >/dev/console 2>&1
echo LYNX_ALPINE_PID1_BEGIN
test "$$" -eq 1
test "$(readlink /proc/1/exe)" = /bin/busybox
test "$(sha256sum /proc/1/exe | cut -d ' ' -f 1)" = BUSYBOX_HASH
echo LYNX_ALPINE_PID1_EXECUTABLE_VERIFIED
mount -t tmpfs -o size=32m,mode=0755 tmpfs /run
mkdir -p /dev/pts
mount -t devpts devpts /dev/pts
ln -s /proc/self/fd /dev/fd
ln -s /dev/pts/ptmx /dev/ptmx
cat /proc/mounts
sh /lynx-userspace-probe.sh
echo LYNX_ALPINE_PID1_PROBE_EXIT=0
echo ram-write-probe > /run/pid1-test
test "$(cat /run/pid1-test)" = ram-write-probe
test "$(stat -f -c %T /run)" = tmpfs
test -r /sys/devices/system/cpu/online
echo LYNX_ALPINE_PID1_RAM_AND_SYSFS_PASS
echo LYNX_ALPINE_PID1_PASS
sync
poweroff -f
echo LYNX_ALPINE_PID1_POWEROFF_RETURNED
while :; do sleep 60; done
'''.replace('BUSYBOX_HASH', alpine_busybox_hash).encode()
    put(entries, 'init', init)
    put(entries, 'lynx-userspace-probe.sh', PROBE.encode(), 0o100600)
    # The archive is the root filesystem: no chroot or outer static BusyBox.
    out = ROOT / 'linux-port/artifacts' / ('emulated-alpine-pid1-' + str(time.time_ns()))
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
    report = {'started_ns': time.time_ns(), 'passed': False, 'command': command,
              'rootfs_receipt': str(args.rootfs_receipt.resolve()), 'inventory': inventory,
              'kernel_sha256': hashlib.sha256(boot['kernel']).hexdigest(),
              'init_sha256': hashlib.sha256(init).hexdigest(),
              'alpine_busybox_sha256': alpine_busybox_hash,
              'phone_contacted': False, 'network_enabled': False, 'disk_attached': False,
              'limits': 'Alpine shell as VM PID 1, not OpenRC or a new handset boot. No handset drivers tested.'}
    (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    started = time.monotonic()
    try:
        process = subprocess.run(command, env=environment, capture_output=True, timeout=55)
        console, rc, timed_out = process.stdout + process.stderr, process.returncode, False
    except subprocess.TimeoutExpired as error:
        console, rc, timed_out = (error.stdout or b'') + (error.stderr or b''), None, True
    (out / 'console.log').write_bytes(console)
    checks = {
        'pid1_executable_verified': b'LYNX_ALPINE_PID1_EXECUTABLE_VERIFIED\r\n' in console,
        'userspace_probe_passed': b'LYNX_ALPINE_USERSPACE_PASS\r\n' in console,
        'probe_exit_zero': b'LYNX_ALPINE_PID1_PROBE_EXIT=0\r\n' in console,
        'ram_and_sysfs_passed': b'LYNX_ALPINE_PID1_RAM_AND_SYSFS_PASS\r\n' in console,
        'pid1_passed': b'LYNX_ALPINE_PID1_PASS\r\n' in console,
        'matching_kernel': b'5.10.149-android12-9-o-g311738fbb5a8' in console,
        'clean_poweroff': b'reboot: Power down' in console,
        'poweroff_did_not_return': b'LYNX_ALPINE_PID1_POWEROFF_RETURNED\r\n' not in console,
        'no_kernel_panic': b'Kernel panic' not in console,
    }
    report.update(checks=checks, passed=rc == 0 and not timed_out and all(checks.values()),
                  exit_code=rc, timed_out=timed_out, elapsed_seconds=time.monotonic() - started,
                  finished_ns=time.time_ns(), console_sha256=hashlib.sha256(console).hexdigest())
    (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'passed': report['passed'], 'result': str(out / 'result.json')}))
    if not report['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
