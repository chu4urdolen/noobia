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
    output = PROJECT / 'artifacts' / ('emulated-mtu3-registration-guard-' + str(time.time_ns()))
    output.mkdir()
    reference = (PROJECT / 'artifacts/busybox-August-boot-proof-bound-guards/nord3-busybox-candidate.img').read_bytes()
    require(hashlib.sha256(reference).hexdigest() == 'a9a72334185a5ddec9b6e3ece6e9e01600582f62c4db7bebc8ce87c4d5c3fe43', 'Minimal reference changed')
    boot = read_boot_v4(reference)
    require(hashlib.sha256(boot['kernel']).hexdigest() == 'cbc9f5dc54b5198ddd1e82d5d7bde96f43cbb383a663726ddd68919b0639d3af', 'Kernel changed')
    entries = read_newc(decompress(boot['ramdisk']))
    require(hashlib.sha256(entries['lib/modules/mtu3.ko']['data']).hexdigest() == 'd3c59fa794a6e02f014dd0de660592bb66c9d7f8eb941c1d1183f8a3322bb467', 'Expected original stock MTU3')
    init = b"""#!/bin/sh
export PATH=/bin:/sbin
BB=/bin/busybox
$BB mount -t proc proc /proc
$BB mount -t sysfs sysfs /sys
$BB mount -t tmpfs tmpfs /dev
$BB mknod -m 600 /dev/console c 5 1
$BB mknod -m 666 /dev/null c 1 3
exec > /dev/console 2>&1
found=0
for dev in /sys/bus/platform/devices/*; do
    [ -e "$dev/driver_override" ] || continue
    [ -L "$dev/driver" ] && continue
    before=$($BB cat "$dev/driver_override") || continue
    case "$before" in ''|'(null)') ;; *) continue ;; esac
    printf 'lynx-override-vm-test\\n' > "$dev/driver_override" || continue
    after=$($BB cat "$dev/driver_override") || continue
    [ "$after" = lynx-override-vm-test ] || continue
    printf '\\n' > "$dev/driver_override" || continue
    cleared=$($BB cat "$dev/driver_override") || continue
    case "$cleared" in ''|'(null)') ;; *) continue ;; esac
    printf 'LYNX_VM_OVERRIDE_VERIFIED %s\\n' "$dev"
    found=1
    break
done
[ "$found" = 1 ] || echo LYNX_VM_OVERRIDE_NO_TARGET
"""
    guard = (PROJECT / 'mtu3-registration-guard.sh').read_bytes()
    init += guard.replace(b'/sys/bus/platform/devices', b'/run/fixture/platform').replace(b'/sys/firmware/devicetree/base', b'/run/fixture/dt')
    init += b'log() { printf \'LYNX_VM_REGISTRATION: %s\\n\' "$*"; }\nfixture_target() {\n    port=$1\n    $BB mkdir -p "/run/fixture/platform/$port" "/run/fixture/dt/soc/$port"\n    printf \'mediatek,mtu3\\000mediatek,mt6983-mtu3\\000\' > "/run/fixture/dt/soc/$port/compatible"\n    $BB ln -s "/run/fixture/dt/soc/$port" "/run/fixture/platform/$port/of_node"\n    printf \'(null)\\n\' > "/run/fixture/platform/$port/driver_override"\n}\npassed=0\nfor test in valid-two missing-attr bound unexpected-node existing-override bad-second no-target; do\n    $BB rm -rf /run/fixture\n    $BB mkdir -p /run/fixture/platform /run/fixture/dt/soc\n    expected=74\n    case "$test" in\n        valid-two) fixture_target usb0@11201000; fixture_target usb1@11211000; expected=0 ;;\n        missing-attr) fixture_target usb0@11201000; $BB rm /run/fixture/platform/usb0@11201000/driver_override ;;\n        bound) fixture_target usb0@11201000; $BB ln -s /does-not-exist /run/fixture/platform/usb0@11201000/driver ;;\n        unexpected-node) fixture_target usb2@99990000 ;;\n        existing-override) fixture_target usb0@11201000; printf \'keep-me\\n\' > /run/fixture/platform/usb0@11201000/driver_override ;;\n        bad-second) fixture_target usb0@11201000; fixture_target usb1@11211000; $BB ln -s /does-not-exist /run/fixture/platform/usb1@11211000/driver ;;\n        no-target) ;;\n    esac\n    lynx_mtu3_registration_guard\n    status=$?\n    [ "$status" = "$expected" ] || { echo "LYNX_VM_CASE_FAILED $test status=$status"; break; }\n    good=1\n    for file in /run/fixture/platform/*/driver_override; do\n        [ -f "$file" ] || continue\n        value=$($BB cat "$file")\n        if [ "$expected" = 0 ]; then\n            [ "$value" = lynx-block-mtu3-probe ] || good=0\n        elif [ "$test" = existing-override ]; then\n            [ "$value" = keep-me ] || good=0\n        else\n            [ "$value" = \'(null)\' ] || good=0\n        fi\n    done\n    [ "$good" = 1 ] || { echo "LYNX_VM_CASE_FAILED $test unexpected-write"; break; }\n    passed=$((passed+1))\n    printf \'LYNX_VM_CASE_PASSED %s\\n\' "$test"\ndone\nprintf \'LYNX_VM_GUARD_CASES_PASSED=%s\\n\' "$passed"\n/bin/boot-proof-reboot\nwhile :; do $BB sleep 60; done\n'
    entries['init']['data'] = init
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
    passed = code == 0 and not timed_out and b'LYNX_VM_OVERRIDE_VERIFIED' in raw and b'LYNX_VM_GUARD_CASES_PASSED=7' in raw and b'LYNX_VM_CASE_FAILED' not in raw and b"Restarting system with command 'bootloader'" in raw
    result = dict(passed=passed, phone_contacted=False, exit_code=code, timed_out=timed_out, elapsed_seconds=time.monotonic()-started, command=command, guard_source_sha256=hashlib.sha256(guard).hexdigest(), fixture_cases_passed=7 if b'LYNX_VM_GUARD_CASES_PASSED=7' in raw else None, kernel_sha256=hashlib.sha256(boot['kernel']).hexdigest(), busybox_sha256=hashlib.sha256(entries['bin/busybox']['data']).hexdigest(), console_sha256=hashlib.sha256(raw).hexdigest(), limits='Checks real driver_override write/read/clear on an unbound virt platform device under exact kernel. No MT6983 probe or module matching is exercised; not a handset image.')
    (output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(dict(passed=passed, report=str(output / 'result.json')), indent=2))
    require(passed, 'Native driver_override VM test failed; see console.log')


if __name__ == '__main__':
    main()
