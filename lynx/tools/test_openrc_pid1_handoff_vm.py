"""Test a BusyBox-to-Alpine/OpenRC PID 1 handoff under the frozen stock kernel."""
import argparse
import hashlib
import gzip
import json
import os
import stat
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'linux-port'))
from image_formats import read_boot_v4, read_newc, require
from prepare_busybox_diagnostics import pack
from ramdisk_codec import decompress

V19_SHA256 = '5ce2dbf8a7c132fa7e31f6be70aa76f83afe8c293e2cd5f02251a532486fd851'
RUNTIME = ROOT / 'linux-port/artifacts/openrc-runtime-root'
ROOTFS_ARCHIVE = ROOT / 'linux-port/artifacts/openrc-rootfs-export/alpine-openrc-rootfs.cpio.gz'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sources = parser.add_mutually_exclusive_group()
    sources.add_argument('--runtime-root', type=Path, default=RUNTIME)
    sources.add_argument('--rootfs-cpio-gz', type=Path)
    parser.add_argument('--exercise-production-handoff', action='store_true',
                        help='Exercise openrc-handoff.sh itself with a test-only guard fixture')
    args = parser.parse_args()
    runtime = None
    if args.rootfs_cpio_gz:
        archive_path = args.rootfs_cpio_gz.resolve(strict=True)
        manifest_path = archive_path.parent / 'manifest.json'
        manifest = json.loads(manifest_path.read_text())
        archive_bytes = archive_path.read_bytes()
        require(manifest.get('state') == 'verified-openrc-rootfs-payload' and
                sha(archive_bytes) == manifest.get('archive_sha256'),
                'OpenRC rootfs archive does not match its manifest')
        base_entries = read_newc(gzip.decompress(archive_bytes))
        require({'bin/busybox', 'lib/ld-musl-aarch64.so.1', 'sbin/openrc-init'}
                <= set(base_entries), 'OpenRC rootfs archive lacks required files')
        source_label = str(archive_path)
    else:
        runtime = args.runtime_root.resolve(strict=True)
        require((runtime / 'sbin/openrc-init').is_file() and
                not (runtime / 'sbin/openrc-init').is_symlink(), 'OpenRC runtime missing')
        base_entries = {}
        source_label = str(runtime)

    out = ROOT / 'linux-port/artifacts' / ('openrc-pid1-handoff-vm-' + str(time.time_ns()))
    out.mkdir(mode=0o700)
    source = ROOT / 'linux-port/artifacts/busybox-wifi-ssh-twostage-v19/nord3-busybox-candidate.img'
    image = source.read_bytes()
    require(sha(image) == V19_SHA256, 'Frozen V19 stock-kernel fixture changed')
    boot = read_boot_v4(image)
    entries = read_newc(decompress(boot['ramdisk']))
    total = 0
    for name in ('mnt', 'mnt/alpine'):
        entries[name] = {'mode': stat.S_IFDIR | 0o755, 'uid': 0, 'gid': 0,
                         'rdevmajor': 0, 'rdevminor': 0, 'data': b''}

    # Embed the Alpine root at /mnt/alpine. The existing PID 1 binds the live
    # proc, sys, dev and run mounts into it, then replaces itself with OpenRC.
    if runtime is not None:
        for path in sorted(runtime.rglob('*')):
            rel = path.relative_to(runtime).as_posix()
            info = path.lstat()
            mode = info.st_mode
            if stat.S_ISDIR(mode):
                data, cpio_mode = b'', stat.S_IFDIR | stat.S_IMODE(mode)
            elif stat.S_ISREG(mode):
                data, cpio_mode = path.read_bytes(), stat.S_IFREG | stat.S_IMODE(mode)
            elif stat.S_ISLNK(mode):
                data, cpio_mode = os.readlink(path).encode(), stat.S_IFLNK | stat.S_IMODE(mode)
            else:
                raise ValueError('Unsupported OpenRC root member: ' + rel)
            base_entries[rel] = {'mode': cpio_mode, 'uid': 0, 'gid': 0,
                                 'rdevmajor': 0, 'rdevminor': 0, 'data': data}
    for rel, item in base_entries.items():
        target = 'mnt/alpine/' + rel
        if (rel.startswith('/') or '..' in Path(rel).parts or
                not rel or target in entries):
            raise ValueError('Unsafe or duplicate OpenRC root member: ' + rel)
        mode = item['mode']
        if not (stat.S_ISDIR(mode) or stat.S_ISREG(mode) or stat.S_ISLNK(mode)):
            raise ValueError('Unsupported OpenRC root member type: ' + rel)
        if stat.S_ISREG(mode):
            total += len(item['data'])
        entries[target] = item

    # The runtime image contains no default service links by design. This one
    # checks that a process started under the old PID 1 survived the handoff.
    test_service = {
        'mode': stat.S_IFREG | 0o755, 'uid': 0, 'gid': 0,
        'rdevmajor': 0, 'rdevminor': 0,
        'data': b'''#!/sbin/openrc-run\n\nstart() {\n    pid=$(cat /run/lynx/handoff-worker.pid) || return 1\n    kill -0 "$pid" || return 1\n    echo LYNX_OPENRC_INHERITED_WORKER_PASS > /dev/console\n    ( /bin/busybox sleep 2; echo LYNX_OPENRC_HANDOFF_SHUTDOWN > /dev/console; /sbin/openrc-shutdown --poweroff now ) </dev/null >/dev/console 2>&1 &\n    return 0\n}\n''',
    }
    test_link = {
        'mode': stat.S_IFLNK | 0o777, 'uid': 0, 'gid': 0,
        'rdevmajor': 0, 'rdevminor': 0,
        'data': b'../../init.d/lynx-handoff-proof',
    }
    entries['mnt/alpine/etc/init.d/lynx-handoff-proof'] = test_service
    entries['mnt/alpine/etc/runlevels/default/lynx-handoff-proof'] = test_link
    if args.exercise_production_handoff:
        # Repack the exact exported OpenRC root plus only the existing test
        # service, then exercise the production extraction/hash/mount/exec
        # script. The safety guard is stubbed because QEMU has no Lynx sensors.
        root_entries = dict(base_entries)
        for name, item in (('etc/init.d/lynx-handoff-proof', test_service),
                           ('etc/runlevels/default/lynx-handoff-proof', test_link)):
            for index in range(1, len(Path(name).parts)):
                parent = '/'.join(Path(name).parts[:index])
                root_entries.setdefault(parent, {'mode': stat.S_IFDIR | 0o755, 'uid': 0, 'gid': 0,
                                                 'rdevmajor': 0, 'rdevminor': 0, 'data': b''})
            root_entries[name] = item
        root_archive = gzip.compress(decompress(pack(dict(sorted(root_entries.items(), key=lambda pair: (
            not stat.S_ISDIR(pair[1]['mode']), pair[0].count('/'), pair[0]))))), mtime=0)
        root_hash = sha(root_archive)
        def add_outer(name, data, mode=stat.S_IFREG | 0o644):
            parts = Path(name).parts
            for index in range(1, len(parts)):
                parent = '/'.join(parts[:index])
                entries.setdefault(parent, {'mode': stat.S_IFDIR | 0o755, 'uid': 0, 'gid': 0,
                                            'rdevmajor': 0, 'rdevminor': 0, 'data': b''})
            entries[name] = {'mode': mode, 'uid': 0, 'gid': 0,
                             'rdevmajor': 0, 'rdevminor': 0, 'data': data}
        add_outer('usr/share/lynx/alpine-openrc-rootfs.cpio.gz', root_archive)
        add_outer('usr/share/lynx/alpine-openrc-rootfs.sha256', (root_hash + '\n').encode())
        add_outer('etc/lynx/session-token', b'test-openrc-token\n')
        add_outer('etc/lynx/host-ip', b'192.168.100.1\n')
        add_outer('etc/lynx/openrc-handoff-guard.sh',
                  b'lynx_openrc_handoff_guard() { echo OPENRC_HANDOFF_TEST_GUARD_PASS; }\n',
                  stat.S_IFREG | 0o755)
        add_outer('etc/lynx/openrc-handoff.sh', (ROOT / 'linux-port/openrc-handoff.sh').read_bytes(),
                  stat.S_IFREG | 0o755)
        init = b'''#!/bin/busybox sh\nset -eu\nexport PATH=/bin:/sbin:/usr/bin:/usr/sbin\nBB=/bin/busybox\nlog() { echo "$*" > /dev/kmsg; }\n$BB mkdir -p /proc /sys /dev /run/lynx\n$BB mount -t proc -o nosuid,nodev,noexec proc /proc\n$BB mount -t sysfs -o nosuid,nodev,noexec sysfs /sys\n$BB mount -t tmpfs -o mode=0755,size=16m tmpfs /dev\n$BB mknod -m 600 /dev/console c 5 1\n$BB mknod -m 666 /dev/null c 1 3\nexec </dev/console >/dev/console 2>&1\n$BB mount -t tmpfs -o mode=0755,size=32m tmpfs /run\n$BB mkdir -p /run/lynx\n$BB printf '%s\\n' test-openrc-token > /run/lynx/host-confirmed\n$BB printf '%s\\n' test-openrc-token > /run/lynx/openrc-handoff-ready\n$BB sh -c 'echo $$ > /run/lynx/handoff-worker.pid; while :; do /bin/busybox sleep 1; done' &\necho LYNX_BUSYBOX_EARLY_INIT_READY > /dev/console\n. /etc/lynx/openrc-handoff.sh\nlynx_openrc_handoff\n'''
    else:
        init = b'''#!/bin/busybox sh\nset -eu\nBB=/bin/busybox\n$BB mkdir -p /proc /sys /dev /run/lynx /mnt/alpine/proc /mnt/alpine/sys /mnt/alpine/dev /mnt/alpine/run\n$BB mount -t proc -o nosuid,nodev,noexec proc /proc\n$BB mount -t sysfs -o nosuid,nodev,noexec sysfs /sys\n$BB mount -t tmpfs -o mode=0755,size=16m tmpfs /dev\n$BB mknod -m 600 /dev/console c 5 1\n$BB mknod -m 666 /dev/null c 1 3\nexec </dev/console >/dev/console 2>&1\n$BB mount -t tmpfs -o mode=0755,size=32m tmpfs /run\n$BB mkdir -p /run/lynx\n$BB sh -c 'echo $$ > /run/lynx/handoff-worker.pid; while :; do /bin/busybox sleep 1; done' &\n$BB mount -o bind /proc /mnt/alpine/proc\n$BB mount -o bind /sys /mnt/alpine/sys\n$BB mount -o bind /dev /mnt/alpine/dev\n$BB mount -o bind /run /mnt/alpine/run\n$BB ls -l /mnt/alpine/sbin/openrc-init /mnt/alpine/lib/ld-musl-aarch64.so.1 > /dev/console\n$BB chroot /mnt/alpine /bin/busybox echo LYNX_CHROOT_EXEC_PASS > /dev/console\necho LYNX_BUSYBOX_EARLY_INIT_READY > /dev/console\nexec $BB chroot /mnt/alpine /sbin/openrc-init\n'''
    entries['init'] = {'mode': stat.S_IFREG | 0o755, 'uid': 0, 'gid': 0,
                       'rdevmajor': 0, 'rdevminor': 0, 'data': init}
    for name, major, minor, mode in [('dev/console', 5, 1, 0o600),
                                      ('dev/null', 1, 3, 0o666)]:
        entries[name] = {'mode': stat.S_IFCHR | mode, 'uid': 0, 'gid': 0,
                         'rdevmajor': major, 'rdevminor': minor, 'data': b''}
    ramdisk = pack(dict(sorted(entries.items(), key=lambda pair: (
        not stat.S_ISDIR(pair[1]['mode']), pair[0].count('/'), pair[0]))))
    (out / 'init-source').write_bytes(init)
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
    started_ns = time.time_ns()
    started = time.monotonic()
    with (out / 'console.log').open('wb') as console:
        try:
            proc = subprocess.run(command, env=env, stdout=console,
                                  stderr=subprocess.STDOUT, timeout=15)
            rc, timed_out = proc.returncode, False
        except subprocess.TimeoutExpired:
            rc, timed_out = None, True
    output = (out / 'console.log').read_bytes()
    checks = {
        'busybox_early_init_ran': b'LYNX_BUSYBOX_EARLY_INIT_READY' in output,
        'chroot_dynamic_busybox_exec': (args.exercise_production_handoff or
                                        b'LYNX_CHROOT_EXEC_PASS' in output),
        'openrc_replaced_pid1': b'OpenRC init version 0.63.2 starting' in output,
        'production_handoff_guard_invoked': (not args.exercise_production_handoff or
                                             b'OPENRC_HANDOFF_TEST_GUARD_PASS' in output),
        'inherited_early_worker_survived': b'LYNX_OPENRC_INHERITED_WORKER_PASS' in output,
        'clean_poweroff': b'reboot: Power down' in output,
        'no_kernel_panic': b'Kernel panic' not in output,
    }
    passed = rc == 0 and not timed_out and all(checks.values())
    report = {
        'state': 'openrc-pid1-handoff-verified' if passed else 'failed',
        'started_ns': started_ns, 'finished_ns': time.time_ns(),
        'runtime_root_source': source_label,
        'runtime_root_regular_bytes': total,
        'kernel_sha256': sha(boot['kernel']), 'ramdisk_sha256': sha(ramdisk),
        'ramdisk_bytes': len(ramdisk), 'checks': checks, 'exit_code': rc,
        'timed_out': timed_out, 'elapsed_seconds': time.monotonic() - started,
        'network_enabled': False, 'phone_contacted': False,
        'phone_boot_or_partition_changed': False,
        'production_handoff_script_tested': args.exercise_production_handoff,
        'limits': 'QEMU-only PID 1 handoff proof; test guard is stubbed because the VM has no Lynx sensor hardware. Does not test V19 phone-specific driver/Wi-Fi startup or a handset boot image.',
    }
    (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'state': report['state'], 'result': str(out / 'result.json')}))
    if not passed:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
