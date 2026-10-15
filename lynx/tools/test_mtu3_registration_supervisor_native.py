"""Real ARM64 BusyBox supervisor and stock module in isolated stock-kernel QEMU."""
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
PROJECT = ROOT / 'linux-port'
sys.path.insert(0, str(PROJECT))
from image_formats import read_boot_v4, read_newc, require
from ramdisk_codec import decompress
from prepare_busybox_diagnostics import pack


def main():
    output = PROJECT / 'artifacts' / ('emulated-mtu3-registration-supervisor-' + str(time.time_ns()))
    output.mkdir()
    reference = (PROJECT / 'artifacts/busybox-August-boot-proof-bound-guards/nord3-busybox-candidate.img').read_bytes()
    require(hashlib.sha256(reference).hexdigest() == 'a9a72334185a5ddec9b6e3ece6e9e01600582f62c4db7bebc8ce87c4d5c3fe43', 'Minimal reference changed')
    boot = read_boot_v4(reference)
    require(hashlib.sha256(boot['kernel']).hexdigest() == 'cbc9f5dc54b5198ddd1e82d5d7bde96f43cbb383a663726ddd68919b0639d3af', 'Kernel changed')
    entries = read_newc(decompress(boot['ramdisk']))
    require(hashlib.sha256(entries['lib/modules/mtu3.ko']['data']).hexdigest() == 'd3c59fa794a6e02f014dd0de660592bb66c9d7f8eb941c1d1183f8a3322bb467', 'Expected original stock MTU3')
    guard = (PROJECT / 'mtu3-registration-guard.sh').read_bytes()
    supervisor = guard.replace(b'/sys/bus/platform/devices', b'/run/fixture/platform').replace(b'/sys/firmware/devicetree/base', b'/run/fixture/dt') + (PROJECT / 'mtu3-timed-supervisor.sh').read_bytes().replace(b'$BB insmod /lib/modules/mtu3.ko', b'lynx_mtu3_registration_load')
    # This test init deliberately tests only userspace and module registration
    # on virt. It is not a handset candidate and has no MT6983 reset guard.
    init = b'''#!/bin/sh
export PATH=/bin:/sbin
BB=/bin/busybox
$BB mount -t proc proc /proc
$BB mount -t sysfs sysfs /sys
$BB mount -t tmpfs tmpfs /dev
$BB mknod -m 600 /dev/console c 5 1
exec > /dev/console 2>&1
log() { printf 'LYNX_VM_SUPERVISOR: %s\\n' "$*"; }
'''
    init += b"$BB mkdir -p /run/fixture/platform/usb0 /run/fixture/dt/soc/usb0@11201000\nprintf 'mediatek,mtu3\\000mediatek,mt6983-mtu3\\000' > /run/fixture/dt/soc/usb0@11201000/compatible\n$BB ln -s /run/fixture/dt/soc/usb0@11201000 /run/fixture/platform/usb0/of_node\nprintf '(null)\\n' > /run/fixture/platform/usb0/driver_override\n"
    init += supervisor + b"\nlynx_mtu3_supervise || log 'SUPERVISOR_FAILED'\nwhile :; do $BB sleep 60; done\n"
    entries['init']['data'] = init
    entries['bin/vm-reboot'] = dict(entries['bin/boot-proof-reboot'])
    entries['bin/boot-proof-reboot']['data'] = b'''#!/bin/sh
printf 'LYNX_VM_CHILD_RESULT='
/bin/busybox cat /run/mtu3-result
printf 'LYNX_VM_REBOOT_UPTIME='
/bin/busybox cat /proc/uptime
exec /bin/vm-reboot
'''
    stock = PROJECT / 'artifacts/stock-cph2493-August-eu-ota'
    (output / 'Image').write_bytes(gzip.decompress(boot['kernel']))
    (output / 'initramfs').write_bytes((stock / 'unpacked-vendor-boot/vendor_ramdisk00').read_bytes() + pack(entries))
    (output / 'init-source').write_bytes(init)
    runtime = ROOT / 'tools/qemu/noble/root'
    command = [str(runtime / 'usr/bin/qemu-system-aarch64'), '-L', str(runtime / 'usr/share/qemu'), '-no-user-config', '-nodefaults', '-machine', 'virt,gic-version=3', '-accel', 'tcg', '-cpu', 'cortex-a72', '-smp', '2', '-m', '1024', '-display', 'none', '-monitor', 'none', '-serial', 'stdio', '-nic', 'none', '-no-reboot', '-kernel', str(output / 'Image'), '-initrd', str(output / 'initramfs'), '-append', 'console=ttyAMA0 rdinit=/init loglevel=7 panic=0']
    env = dict(os.environ, LD_LIBRARY_PATH=str(runtime / 'usr/lib/x86_64-linux-gnu'), QEMU_MODULE_DIR=str(runtime / 'usr/lib/x86_64-linux-gnu/qemu'), TMPDIR=str(ROOT / 'tools/mtk-tmp'))
    started = time.monotonic()
    try:
        process = subprocess.run(command, env=env, capture_output=True, timeout=45)
        raw = process.stdout + process.stderr
        code, timed_out = process.returncode, False
    except subprocess.TimeoutExpired as error:
        raw = (error.stdout or b'') + (error.stderr or b'')
        code, timed_out = None, True
    (output / 'console.log').write_bytes(raw)
    first = re.search(rb'MTU3_CHILD_STARTED pid=\d+ boot_seconds=(\d+)', raw)
    reset = re.search(rb'LYNX_VM_REBOOT_UPTIME=(\d+(?:\.\d+)?)', raw)
    delay = float(reset.group(1)) - int(first.group(1)) if first and reset else None
    passed = b'MTU3_REGISTRATION_ONLY_GUARD_VERIFIED targets=1' in raw and code == 0 and not timed_out and b'LYNX_VM_CHILD_RESULT=0' in raw and b'MTU3_OUTCOME load-returned-success' in raw and b"Restarting system with command 'bootloader'" in raw and delay is not None and 20 <= delay < 22
    result = dict(guard_source_sha256=hashlib.sha256(guard).hexdigest(), fixture_guard_used=True, passed=passed, phone_contacted=False, stock_module_registered=True if b'LYNX_VM_CHILD_RESULT=0' in raw else False, child_relative_reset_seconds=delay, exit_code=code, timed_out=timed_out, elapsed_seconds=time.monotonic()-started, command=command, supervisor_source_sha256=hashlib.sha256(supervisor).hexdigest(), busybox_sha256=hashlib.sha256(entries['bin/busybox']['data']).hexdigest(), console_sha256=hashlib.sha256(raw).hexdigest(), limits='Tests actual BusyBox fork/insmod/mv/tmpfs/proc clock and20-second path under exact kernel on virt. No MT6983 hardware probe runs; not a handset image.')
    (output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(dict(passed=passed, report=str(output / 'result.json'), child_relative_reset_seconds=delay), indent=2))
    require(passed, 'Native supervisor VM test failed; see console.log')


if __name__ == '__main__':
    main()
