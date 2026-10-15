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
from network_userspace import add_network_userspace


def main():
    output = PROJECT / 'artifacts' / ('emulated-native-calibration-readonly-' + str(time.time_ns()))
    output.mkdir()
    reference = (PROJECT / 'artifacts/busybox-August-boot-proof-bound-guards/nord3-busybox-candidate.img').read_bytes()
    require(hashlib.sha256(reference).hexdigest() == 'a9a72334185a5ddec9b6e3ece6e9e01600582f62c4db7bebc8ce87c4d5c3fe43', 'Minimal reference changed')
    boot = read_boot_v4(reference)
    require(hashlib.sha256(boot['kernel']).hexdigest() == 'cbc9f5dc54b5198ddd1e82d5d7bde96f43cbb383a663726ddd68919b0639d3af', 'Kernel changed')
    entries = read_newc(decompress(boot['ramdisk']))
    require(hashlib.sha256(entries['lib/modules/mtu3.ko']['data']).hexdigest() == 'd3c59fa794a6e02f014dd0de660592bb66c9d7f8eb941c1d1183f8a3322bb467', 'Expected original stock MTU3')
    from network_userspace import put
    filesystem=Path(json.loads((ROOT/'tools/test-artifacts/wifi-calibration-fixture-current.json').read_text())['image']).read_bytes()
    put(entries,'bin/test-nvdata.ext4',filesystem,0o100600)
    helper=(PROJECT/'artifacts/wifi-native-helpers/lynx-wifi-control.elf').read_bytes()
    put(entries,'bin/lynx-wifi-control',helper)
    calibration=(PROJECT/'lynx-calibration-readonly.sh').read_bytes()
    init=b'#!/bin/sh\nexport PATH=/bin:/sbin:/usr/bin:/usr/sbin\nBB=/bin/busybox\n$BB mount -t proc proc /proc\n$BB mount -t sysfs sysfs /sys\n$BB mount -t tmpfs tmpfs /dev\n$BB mount -t tmpfs tmpfs /run\n$BB mknod -m 600 /dev/console c 5 1\n$BB mknod -m 666 /dev/null c 1 3\n$BB mknod -m 600 /dev/kmsg c 1 11\nexec > /dev/console 2>&1\n$BB mdev -s\nlog() { printf \'LYNX_VM_CALIBRATION: %s\\n\' "$*"; }\n$BB losetup /dev/loop0 /bin/test-nvdata.ext4\n$BB mkdir -p /run/fixture/loop0\nprintf \'PARTNAME=nvdata\\nDEVNAME=loop0\\n\' > /run/fixture/loop0/uevent\n'
    init+=calibration.replace(b'/sys/class/block',b'/run/fixture')
    put(entries,'bin/expected-WIFI',bytes([90])*256,0o100600)
    init+=b'\nlynx_read_factory_calibration\nstatus=$?\nprintf \'LYNX_VM_CALIBRATION_EXIT=%s\\n\' "$status"\n$BB cmp /run/lynx/calibration/WIFI /bin/expected-WIFI && echo LYNX_VM_CALIBRATION_BYTES_MATCH\nro=$($BB blockdev --getro /dev/loop0)\nprintf \'LYNX_VM_BLOCK_READONLY=%s\\n\' "$ro"\n# Refuse a regular file as a hardware-control endpoint.\nprintf \'DO_NOT_MODIFY\\n\' > /dev/wmtWifi\n/bin/lynx-wifi-control --nvram\nprintf \'LYNX_VM_NONCHAR_NVRAM_EXIT=%s\\n\' "$?"\n/bin/lynx-wifi-control --station\nprintf \'LYNX_VM_NONCHAR_STATION_EXIT=%s\\n\' "$?"\n$BB grep -q \'^DO_NOT_MODIFY$\' /dev/wmtWifi && echo LYNX_VM_NONCHAR_UNCHANGED\n/bin/lynx-wifi-control --chip\nprintf \'LYNX_VM_ABSENT_CHIP_EXIT=%s\\n\' "$?"\n# Capture one complete driver-RAM frame using the VM-only kmsg sink.\n$BB rm /dev/wmtWifi\n$BB ln -s /dev/kmsg /dev/wmtWifi\n/bin/lynx-wifi-control --nvram\nprintf \'LYNX_VM_NVRAM_FRAME_EXIT=%s\\n\' "$?"\n/bin/boot-proof-reboot\nwhile :; do $BB sleep 60; done\n'
    entries['init']['data']=init
    stock = PROJECT / 'artifacts/stock-cph2493-August-eu-ota'
    (output / 'Image').write_bytes(gzip.decompress(boot['kernel']))
    (output / 'initramfs').write_bytes((stock / 'unpacked-vendor-boot/vendor_ramdisk00').read_bytes() + pack(entries))
    (output / 'init-source').write_bytes(init)
    runtime = ROOT / 'tools/qemu/noble/root'
    command = [str(runtime / 'usr/bin/qemu-system-aarch64'), '-L', str(runtime / 'usr/share/qemu'), '-no-user-config', '-nodefaults', '-machine', 'virt,gic-version=3', '-accel', 'tcg', '-cpu', 'cortex-a72', '-smp', '2', '-m', '1024', '-display', 'none', '-monitor', 'none', '-serial', 'stdio', '-nic', 'none', '-no-reboot', '-kernel', str(output / 'Image'), '-initrd', str(output / 'initramfs'), '-append', 'console=ttyAMA0 rdinit=/init loglevel=7 panic=0']
    env = dict(os.environ, LD_LIBRARY_PATH=str(runtime / 'usr/lib/x86_64-linux-gnu'), QEMU_MODULE_DIR=str(runtime / 'usr/lib/x86_64-linux-gnu/qemu'), TMPDIR=str(ROOT / 'tools/mtk-tmp'))
    started = time.monotonic()
    try:
        process = subprocess.run(command, env=env, capture_output=True, timeout=60)
        raw = process.stdout + process.stderr
        code, timed_out = process.returncode, False
    except subprocess.TimeoutExpired as error:
        raw = (error.stdout or b'') + (error.stderr or b'')
        code, timed_out = None, True
    (output / 'console.log').write_bytes(raw)
    expected=[b'LYNX_VM_CALIBRATION_EXIT=0',b'LYNX_VM_CALIBRATION_BYTES_MATCH',b'LYNX_VM_BLOCK_READONLY=1',b'LYNX_VM_NONCHAR_NVRAM_EXIT=125',b'LYNX_VM_NONCHAR_STATION_EXIT=115',b'LYNX_VM_NONCHAR_UNCHANGED',b'LYNX_VM_ABSENT_CHIP_EXIT=111',b'LYNX_VM_NVRAM_FRAME_EXIT=0',b'WR-BUF:NVRAM'+b'Z'*256]
    passed=code==0 and not timed_out and all(x in raw for x in expected)
    result=dict(passed=passed,phone_contacted=False,exit_code=code,timed_out=timed_out,elapsed_seconds=time.monotonic()-started,command=command,calibration_source_sha256=hashlib.sha256(calibration).hexdigest(),helper_sha256=hashlib.sha256(helper).hexdigest(),console_sha256=hashlib.sha256(raw).hexdigest(),missing_checks=[x[:80].decode(errors='replace') for x in expected if x not in raw],limits='Synthetic ext4 loop device and substituted sysfs discovery root; original ARM64 helper and calibration function otherwise execute under exact stock kernel. Verifies block read-only, ro/noload mounting, byte copy, non-character endpoint refusal and single complete payload. No real phone calibration or radio initialization.')
    (output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(dict(passed=passed, report=str(output / 'result.json')), indent=2))
    require(passed, 'Native network userspace VM test failed; see console.log')


if __name__ == '__main__':
    main()
