"""Run reader protocol tests in ARM64 QEMU with no USB, disks or network."""
import gzip
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

BASE = Path(__file__).resolve().parent
PROJECT = BASE.parent.parent / 'linux-port'
sys.path.insert(0, str(PROJECT))
from image_formats import read_boot_v4, read_newc
from ramdisk_codec import decompress, compress_legacy

candidate = PROJECT / 'artifacts/busybox-August-usb-device-mode/nord3-busybox-candidate.img'
data = candidate.read_bytes()
assert hashlib.sha256(data).hexdigest() == '6b76783a2cd9f2bcbbdb7b45bbc609786bf0e82a6f9376f180dc98703f37f577'
boot = read_boot_v4(data)
assert hashlib.sha256(boot['kernel']).hexdigest() == 'cbc9f5dc54b5198ddd1e82d5d7bde96f43cbb383a663726ddd68919b0639d3af'
original = read_newc(decompress(boot['ramdisk']))
report = json.loads((BASE / 'build-report.json').read_text())
executable = (BASE / 'test-reader-aarch64').read_bytes()
assert hashlib.sha256(executable).hexdigest() == report['files']['test-reader-aarch64']
output = BASE / 'arm-emulation'
output.mkdir(exist_ok=True)
assert not (output / 'result.json').exists(), 'Preserve previous evidence before rerunning'
kernel = output / 'stock-Image'
kernel.write_bytes(gzip.decompress(boot['kernel']))
entries = {}
for name in ['bin', 'bin/busybox', 'bin/sh', 'dev', 'dev/console', 'proc', 'sys']:
    entries[name] = original[name]
init = b'''#!/bin/sh
BB=/bin/busybox
$BB mount -t proc proc /proc || exit 1
$BB mount -t sysfs sysfs /sys || exit 1
/test-reader
reader_status=$?
printf 'LYNX_READER_TEST_EXIT=%s\\n' "$reader_status"
$BB poweroff -f
while :; do $BB sleep 60; done
'''
for name, blob in [('init', init), ('test-reader', executable)]:
    entries[name] = dict(mode=stat.S_IFREG | 0o755, uid=0, gid=0, rdevmajor=0, rdevminor=0, data=blob)
archive = bytearray()
trailer = dict(mode=0, uid=0, gid=0, rdevmajor=0, rdevminor=0, data=b'')
for inode, (name, item) in enumerate([*entries.items(), ('TRAILER!!!', trailer)], 1):
    encoded = name.encode() + b'\0'
    fields = [inode, item['mode'], item['uid'], item['gid'], 1, 0, len(item['data']),
              0, 0, item['rdevmajor'], item['rdevminor'], len(encoded), 0]
    archive += b'070701' + ''.join(f'{value:08x}' for value in fields).encode() + encoded
    archive += b'\0' * (-len(archive) % 4)
    archive += item['data']
    archive += b'\0' * (-len(archive) % 4)
assert read_newc(archive) == entries
ramdisk = output / 'test-initramfs.lz4'
ramdisk.write_bytes(compress_legacy(bytes(archive)))
runtime = BASE.parent / 'qemu/noble/root'
binary = runtime / 'usr/bin/qemu-system-aarch64'
env = dict(os.environ, LD_LIBRARY_PATH=str(runtime / 'usr/lib/x86_64-linux-gnu'),
           QEMU_MODULE_DIR=str(runtime / 'usr/lib/x86_64-linux-gnu/qemu'), TMPDIR=str(BASE))
command = [str(binary), '-L', str(runtime / 'usr/share/qemu'), '-no-user-config', '-nodefaults',
           '-machine', 'virt,gic-version=3', '-accel', 'tcg', '-cpu', 'cortex-a72', '-m', '1024',
           '-display', 'none', '-monitor', 'none', '-serial', 'stdio', '-nic', 'none', '-no-reboot',
           '-kernel', str(kernel), '-initrd', str(ramdisk), '-append', 'console=ttyAMA0 rdinit=/init panic=0']
run = subprocess.run(command, env=env, capture_output=True, timeout=40)
console = (run.stdout + run.stderr).decode(errors='replace').replace('\r', '')
(output / 'console.log').write_text(console)
passed = 'LYNX_READER_ARM_TEST_PASSED\n' in console and 'LYNX_READER_TEST_EXIT=0\n' in console
result = {'command': command, 'qemu_exit_code': run.returncode, 'arm_protocol_tests_passed': passed,
          'test_executable_sha256': hashlib.sha256(executable).hexdigest(),
          'kernel_sha256': hashlib.sha256(boot['kernel']).hexdigest(),
          'device_contacted': False, 'hardware_integration_proven': False,
          'limits': 'ARM64 callback logic with fake channel and synthetic RAM only; no DA entry, heap repair, or device transport.'}
(output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result, indent=2))
assert passed and run.returncode == 0, console[-2000:]
