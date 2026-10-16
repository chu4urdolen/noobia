"""Prepare a pinned offline RAM stage; optionally test cold startup in a VM."""
import argparse
import gzip
import hashlib
import io
import json
import os
import subprocess
import tarfile
import time
from pathlib import Path

from alpine_rootfs import ROOT, ARCHIVE_SHA256, read_rootfs
from image_formats import read_boot_v4, read_newc
from network_userspace import put
from prepare_busybox_diagnostics import pack
from ramdisk_codec import decompress

PACKAGES = ['libbz2=1.0.8-r6', 'libdw=0.195-r0', 'libelf=0.195-r0',
            'musl-fts=1.2.7-r7', 'strace=6.19-r1', 'xz-libs=5.8.4-r0', 'zstd-libs=1.5.7-r2']
V19_HASH = '5ce2dbf8a7c132fa7e31f6be70aa76f83afe8c293e2cd5f02251a532486fd851'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def prepare(rootfs_receipt, package_receipt):
    rootfs, inventory = read_rootfs(rootfs_receipt)
    receipt = json.loads(package_receipt.read_text())
    vm_path = Path(receipt['vm_receipt'])
    vm = json.loads(vm_path.read_text())
    if not (receipt.get('passed') and receipt['base_rootfs_sha256'] == ARCHIVE_SHA256
            and vm.get('passed') and vm['checks'].get('offline_install_and_trace')
            and sha(vm_path.with_name('console.log').read_bytes()) == vm['console_sha256']):
        raise ValueError('Verified base and offline package VM evidence required')
    expected = {spec.replace('=', '-') + '.apk' for spec in PACKAGES}
    hashes = receipt['packages']
    if set(hashes) != expected or hashes != {item['name']: item['sha256'] for item in vm['offline_packages']}:
        raise ValueError('Exact VM-proven diagnostic package set required')
    bundle = Path(receipt['bundle']).read_bytes()
    if sha(bundle) != receipt['sha256']:
        raise ValueError('Offline package bundle changed')
    seen = {}
    with tarfile.open(fileobj=io.BytesIO(bundle), mode='r:gz') as archive:
        for member in archive:
            name = member.name.removeprefix('lynx-offline-apks/')
            if (member.name != 'lynx-offline-apks/' + name or name not in hashes
                    or not member.isfile() or member.size > 16 * 1024 * 1024 or name in seen):
                raise ValueError('Unexpected offline bundle member')
            seen[name] = sha(archive.extractfile(member).read())
    if seen != hashes:
        raise ValueError('Package hashes differ from verified offline VM')
    port = ROOT / 'linux-port'
    members = {'rootfs.tar.gz': Path(inventory['archive']).read_bytes(),
               'diagnostic-apks.tar.gz': bundle,
               'stage.sh': (port / 'alpine-runtime-stage.sh').read_bytes(),
               'observability.sh': (port / 'alpine-observability.sh').read_bytes(),
               'packages.spec': ('\n'.join(PACKAGES) + '\n').encode()}
    essential = ['bin/busybox', 'lib/ld-musl-aarch64.so.1', 'sbin/apk']
    members['essential.sha256'] = ''.join(sha(rootfs[name]['data']) + '  ' + name + '\n' for name in essential).encode()
    members['inputs.sha256'] = ''.join(sha(data) + '  ' + name + '\n' for name, data in sorted(members.items())).encode()
    return members, inventory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rootfs-receipt', type=Path, required=True)
    parser.add_argument('--package-receipt', type=Path, required=True)
    parser.add_argument('--test-vm', action='store_true')
    args = parser.parse_args()
    os.umask(0o077)
    members, inventory = prepare(args.rootfs_receipt, args.package_receipt)
    out = ROOT / 'linux-port/artifacts' / ('alpine-runtime-stage-' + str(time.time_ns()))
    out.mkdir(mode=0o700)
    inputs = out / 'inputs'
    inputs.mkdir(mode=0o700)
    for name, data in members.items():
        (inputs / name).write_bytes(data)
    report = {'prepared': True, 'vm_passed': False, 'started_ns': time.time_ns(),
              'rootfs_receipt': str(args.rootfs_receipt.resolve()), 'package_receipt': str(args.package_receipt.resolve()),
              'inventory': inventory, 'inputs': {name: {'bytes': len(data), 'sha256': sha(data)} for name, data in members.items()},
              'phone_contacted': False, 'flash_performed': False, 'network_enabled': False,
              'limits': 'Optional RAM userspace stage; no handset startup or real driver/thermal initialization tested.'}
    def save():
        (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    save()
    if args.test_vm:
        reference = (ROOT / 'linux-port/artifacts/busybox-wifi-ssh-twostage-v19/nord3-busybox-candidate.img').read_bytes()
        if sha(reference) != V19_HASH:
            raise ValueError('Frozen V19 image changed')
        boot = read_boot_v4(reference)
        known = read_newc(decompress(boot['ramdisk']))
        entries = {}
        put(entries, 'bin/busybox', known['bin/busybox']['data'])
        for applet in ['sh', 'awk', 'cat', 'mount', 'uname']:
            put(entries, 'bin/' + applet, b'busybox', 0o120777)
        for name, data in members.items():
            put(entries, 'inputs/' + name, data, 0o100600)
        init = b'''#!/bin/busybox sh
set -eu
export PATH=/bin
BB=/bin/busybox
trap 'echo LYNX_ALPINE_STAGE_VM_EXIT; $BB poweroff -f' EXIT
$BB mkdir -p /proc /sys /dev /run
$BB mount -t proc proc /proc
$BB mount -t sysfs sysfs /sys
$BB mount -t tmpfs tmpfs /dev
$BB mknod -m 600 /dev/console c 5 1
$BB mknod -m 666 /dev/null c 1 3
exec </dev/console >/dev/console 2>&1
$BB mount -t tmpfs -o size=128m tmpfs /run
$BB mkdir -p /run/lynx/alpine-stage-vm
$BB cp /inputs/* /run/lynx/alpine-stage-vm/
boot=$(cat /proc/sys/kernel/random/boot_id)
# Fixture only: prove a pre-existing background process survives the stage.
$BB sleep 600 & witness=$!
before=$($BB sha256sum /proc/1/exe)
$BB sh /inputs/stage.sh --install "$boot" /run/lynx/alpine-stage-vm
echo LYNX_ALPINE_STAGE_COLD_INSTALL_PASS
$BB sh /inputs/stage.sh --verify "$boot" /run/lynx/alpine-stage-vm
echo LYNX_ALPINE_STAGE_VERIFY_PASS
if $BB sh /inputs/stage.sh --install "$boot" /run/lynx/alpine-stage-vm; then
    echo LYNX_ALPINE_STAGE_UNEXPECTED_REINSTALL
    exit 1
fi
echo LYNX_ALPINE_STAGE_REINSTALL_REFUSED
if $BB sh /inputs/stage.sh --verify wrong-boot-id /run/lynx/alpine-stage-vm; then exit 1; fi
echo LYNX_ALPINE_STAGE_WRONG_BOOT_REFUSED
$BB ln -s /run/lynx/alpine-stage-vm /run/lynx/alpine-stage-link
if $BB sh /inputs/stage.sh --verify "$boot" /run/lynx/alpine-stage-link; then exit 1; fi
echo LYNX_ALPINE_STAGE_SYMLINK_INPUT_REFUSED
echo corrupted >> /run/lynx/alpine-stage-vm/packages.spec
if $BB sh /inputs/stage.sh --verify "$boot" /run/lynx/alpine-stage-vm; then exit 1; fi
echo LYNX_ALPINE_STAGE_TAMPERED_INPUT_REFUSED
$BB cp /inputs/packages.spec /run/lynx/alpine-stage-vm/packages.spec
test "$before" = "$($BB sha256sum /proc/1/exe)"
kill -0 "$witness"
echo LYNX_ALPINE_STAGE_OUTER_RUNTIME_PRESERVED
$BB chroot /run/lynx/alpine-3.24.2 /bin/sh -c 'test "$(cat /proc/sys/kernel/random/boot_id)" = "$1"; /bin/busybox free -m' -- "$boot"
echo LYNX_ALPINE_STAGE_VM_PASS
$BB poweroff -f
'''
        put(entries, 'init', init)
        (out / 'init-source').write_bytes(init)
        (out / 'Image').write_bytes(gzip.decompress(boot['kernel']))
        (out / 'initramfs').write_bytes(pack(entries))
        q = ROOT / 'tools/qemu/noble/root'
        command = [str(q / 'usr/bin/qemu-system-aarch64'), '-L', str(q / 'usr/share/qemu'),
                   '-no-user-config', '-nodefaults', '-machine', 'virt,gic-version=3', '-accel', 'tcg',
                   '-cpu', 'cortex-a710', '-smp', '2', '-m', '1024', '-display', 'none', '-monitor', 'none',
                   '-serial', 'stdio', '-nic', 'none', '-no-reboot', '-kernel', str(out / 'Image'),
                   '-initrd', str(out / 'initramfs'), '-append', 'console=ttyAMA0 rdinit=/init loglevel=7 panic=0']
        report.update(command=command, kernel_sha256=sha(boot['kernel']), init_sha256=sha(init))
        save()
        environment = dict(os.environ, LD_LIBRARY_PATH=str(q / 'usr/lib/x86_64-linux-gnu'),
                           QEMU_MODULE_DIR=str(q / 'usr/lib/x86_64-linux-gnu/qemu'), TMPDIR=str(out))
        started = time.monotonic()
        with (out / 'console.log').open('wb') as stdout:
            try:
                process = subprocess.run(command, env=environment, stdout=stdout, stderr=subprocess.STDOUT, timeout=55)
                rc, timed_out = process.returncode, False
            except subprocess.TimeoutExpired:
                rc, timed_out = None, True
        console = (out / 'console.log').read_bytes()
        markers = ['COLD_INSTALL_PASS', 'VERIFY_PASS', 'REINSTALL_REFUSED', 'WRONG_BOOT_REFUSED',
                   'SYMLINK_INPUT_REFUSED', 'TAMPERED_INPUT_REFUSED', 'OUTER_RUNTIME_PRESERVED', 'VM_PASS']
        checks = {name.lower(): ('LYNX_ALPINE_STAGE_' + name + '\r\n').encode() in console for name in markers}
        checks.update(clean_poweroff=b'reboot: Power down' in console, no_panic=b'Kernel panic' not in console,
                      no_unexpected_reinstall=b'LYNX_ALPINE_STAGE_UNEXPECTED_REINSTALL\r\n' not in console)
        report.update(vm_passed=rc == 0 and not timed_out and all(checks.values()), checks=checks,
                      console_sha256=sha(console), elapsed_seconds=time.monotonic() - started,
                      exit_code=rc, timed_out=timed_out)
    report['finished_ns'] = time.time_ns()
    save()
    print(json.dumps({'prepared': True, 'vm_passed': report['vm_passed'], 'result': str(out / 'result.json')}))
    if args.test_vm and not report['vm_passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
