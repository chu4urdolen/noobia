"""Boot the exact candidate payload in an isolated ARM VM; never touch Lynx."""
import gzip
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import shutil
import subprocess
import time

from image_formats import read_boot_v4, require

base = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument('--candidate-dir', type=Path, default=base / 'artifacts/busybox-offline')
parser.add_argument('--output-dir', type=Path, default=base / 'artifacts/emulated-boot')
parser.add_argument('--prepend-vendor-ramdisk', type=Path, help='Test the real vendor-before-generic concatenation order')
parser.add_argument('--timeout', type=int, default=120)
parser.add_argument('--exercise-usb-init', action='store_true', help='Execute the module/configfs path in the isolated VM; physical USB remains absent')
args = parser.parse_args()
candidate_dir = args.candidate_dir.resolve()
output = args.output_dir.resolve()
require(output.is_relative_to(base / 'artifacts'), 'Emulator output must remain in artifacts')
require(10 <= args.timeout <= 120, 'Bound the emulation time to 10..120 seconds')
output.mkdir(exist_ok=True)
if (output / 'result.json').exists():
    previous = output / ('previous-' + str(time.time_ns()))
    previous.mkdir()
    for name in ('result.json', 'console.log'):
        if (output / name).exists():
            shutil.copyfile(output / name, previous / name)
report = json.loads((candidate_dir / 'build-validation.json').read_text())
candidate_path = candidate_dir / 'nord3-busybox-candidate.img'
candidate = candidate_path.read_bytes()
require(hashlib.sha256(candidate).hexdigest() == report['candidate_sha256'], 'Candidate changed')
parsed = read_boot_v4(candidate)
require(hashlib.sha256(parsed['kernel']).hexdigest() == report['kernel_sha256'], 'Kernel changed')
kernel = gzip.decompress(parsed['kernel'])
kernel_path = output / 'exact-candidate-Image'
ramdisk_path = output / 'emulated-initramfs.ramdisk'
kernel_path.write_bytes(kernel)
vendor_ramdisk = args.prepend_vendor_ramdisk.read_bytes() if args.prepend_vendor_ramdisk else b''
ramdisk_path.write_bytes(vendor_ramdisk + parsed['ramdisk'])

runtime = Path('/noobia/lynx/tools/qemu/noble/root')
binary = runtime / 'usr/bin/qemu-system-aarch64'
env = dict(os.environ)
env.update(LD_LIBRARY_PATH=str(runtime / 'usr/lib/x86_64-linux-gnu'),
           QEMU_MODULE_DIR=str(runtime / 'usr/lib/x86_64-linux-gnu/qemu'),
           TMPDIR='/noobia/lynx/tools/mtk-tmp')
command = [str(binary), '-L', str(runtime / 'usr/share/qemu'), '-no-user-config',
           '-nodefaults', '-machine', 'virt,gic-version=3', '-accel', 'tcg',
           '-cpu', 'cortex-a72', '-smp', '2', '-m', '1024', '-display', 'none',
           '-monitor', 'none', '-serial', 'stdio', '-nic', 'none', '-no-reboot',
           '-kernel', str(kernel_path), '-initrd', str(ramdisk_path),
           '-append', 'console=ttyAMA0 rdinit=/init loglevel=7 panic=0' + (' noobia.usb=1' if args.exercise_usb_init else '')]
process = subprocess.Popen(command, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, bufsize=0)
selector = selectors.DefaultSelector()
selector.register(process.stdout, selectors.EVENT_READ)
started = time.monotonic()
buffer = bytearray()
sent = False
deadline = started + args.timeout
with (output / 'console.log').open('wb') as log:
    while time.monotonic() < deadline:
        for key, events in selector.select(timeout=0.25):
            data = os.read(key.fileobj.fileno(), 65536)
            if not data:
                selector.unregister(key.fileobj)
                continue
            log.write(data)
            log.flush()
            buffer.extend(data)
        if not sent and b'NORD3_NATIVE_LINUX_PID1_OK pid=1' in buffer and re.search(rb'(?:/|~) # ', buffer):
            commands = b"printf 'EMULATED_PID1_COMM=%s\\n' \"$(cat /proc/1/comm)\"; printf 'EMULATED_CPU_ARCH=%s\\n' \"$(uname -m)\"; printf 'EMULATED_DEVTMPFS_MOUNTS=%s\\n' \"$(grep -c '^devtmpfs ' /proc/mounts)\"; poweroff -f\n"
            process.stdin.write(commands)
            process.stdin.flush()
            sent = True
        if process.poll() is not None and not selector.get_map():
            break
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
selector.close()
text = buffer.decode(errors='replace').replace('\r', '')
pid1 = re.search(r'^EMULATED_PID1_COMM=(.+)$', text, re.M)
arch = re.search(r'^EMULATED_CPU_ARCH=(.+)$', text, re.M)
devtmpfs = re.search(r'^EMULATED_DEVTMPFS_MOUNTS=(.+)$', text, re.M)
result = {'candidate_sha256': report['candidate_sha256'], 'kernel_sha256': report['kernel_sha256'],
          'decompressed_kernel_sha256': hashlib.sha256(kernel).hexdigest(),
          'initramfs_sha256': hashlib.sha256(parsed['ramdisk']).hexdigest(),
          'prepended_vendor_ramdisk_sha256': hashlib.sha256(vendor_ramdisk).hexdigest() if vendor_ramdisk else None,
          'combined_initramfs_sha256': hashlib.sha256(vendor_ramdisk + parsed['ramdisk']).hexdigest(),
          'qemu_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(),
          'command': command, 'elapsed_seconds': round(time.monotonic() - started, 2),
          'qemu_exit_code': process.returncode,
          'native_pid1_marker_observed': 'NORD3_NATIVE_LINUX_PID1_OK pid=1' in text,
          'interactive_commands_executed': arch is not None and arch.group(1) == 'aarch64',
          'pid1_comm': pid1.group(1) if pid1 else None,
          'devtmpfs_mounts': devtmpfs.group(1) if devtmpfs else None,
          'phone_contacted': False, 'hardware_boot_proven': False, 'flash_eligible': False,
          'limits': 'QEMU virt tests userspace startup; it does not emulate MT6983 peripherals or prove recovery.'}
(output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result, indent=2))
if not result['native_pid1_marker_observed']:
    print(text[-5000:])
    raise SystemExit(1)
