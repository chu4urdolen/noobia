"""Exercise actual diagnostic module load/unload on stock kernel in ARM QEMU.

No handset, network, or MT6983 gauge is present. This checks loader/CFI entry
compatibility and default refusal, not the I2C probe or battery interpretation.
"""
import argparse
import gzip
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PORT = ROOT / 'linux-port'
sys.path.insert(0, str(PORT))
from image_formats import read_boot_v4, read_newc
from ramdisk_codec import decompress
from network_userspace import put
from prepare_busybox_diagnostics import pack

INIT = b'''#!/bin/busybox sh
BB=/bin/busybox
$BB mkdir -p /proc /sys /dev
$BB mount -t proc proc /proc
$BB mount -t sysfs sysfs /sys
$BB mount -t tmpfs tmpfs /dev
$BB mknod -m 600 /dev/console c 5 1
$BB mknod -m 666 /dev/null c 1 3
exec </dev/console >/dev/console 2>&1
fail() { echo "GAUGE_TEST_FAILURE=$1"; $BB poweroff -f; exit 1; }
echo GAUGE_STOCK_KERNEL_BEGIN
$BB uname -r
$BB insmod /fixture/lynx-gauge-sample.ko >/default-load.log 2>&1
rc=$?
$BB cat /default-load.log
[ "$rc" -ne 0 ] && [ ! -d /sys/module/lynx_gauge_sample ] || fail default_guard
echo GAUGE_DEFAULT_REFUSAL=PASS
$BB insmod /fixture/lynx-gauge-sample.ko allow_raw_read=1 || fail explicit_load
[ -d /sys/module/lynx_gauge_sample ] || fail module_missing
[ -d /sys/bus/i2c/drivers/lynx-gauge-sample ] || fail driver_missing
echo GAUGE_DRIVER_REGISTERED=PASS
$BB cat /proc/modules
$BB rmmod lynx_gauge_sample || fail unload
[ ! -d /sys/module/lynx_gauge_sample ] || fail module_remains
[ ! -d /sys/bus/i2c/drivers/lynx-gauge-sample ] || fail driver_remains
echo GAUGE_UNLOADED=PASS
$BB dmesg
echo GAUGE_STOCK_KERNEL_END
$BB poweroff -f
'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--basis', type=Path, required=True)
    parser.add_argument('--identity-query', action='store_true')
    parser.add_argument('--battery-monitor', action='store_true')
    args = parser.parse_args()
    report = json.loads((args.basis / 'build-result.json').read_text())
    name=report.get('module_name','lynx-gauge-sample')
    module = (args.basis / 'module' / (name+'.ko')).read_bytes()
    digest = hashlib.sha256(module).hexdigest()
    if not report['passed'] or digest != report['module_sha256']:
        raise ValueError('Successful build receipt does not match module')
    boot_raw = (PORT / 'artifacts/busybox-wifi-ssh-twostage-v19/nord3-busybox-candidate.img').read_bytes()
    if hashlib.sha256(boot_raw).hexdigest() != '5ce2dbf8a7c132fa7e31f6be70aa76f83afe8c293e2cd5f02251a532486fd851':
        raise ValueError('V19 reference changed')
    boot = read_boot_v4(boot_raw)
    original = read_newc(decompress(boot['ramdisk']))
    entries = {}
    put(entries, 'bin/busybox', original['bin/busybox']['data'])
    init = INIT.replace(b'allow_raw_read=1', b'allow_identity_query=1').replace(b'/drivers/lynx-gauge-sample', b'/drivers/lynx-gauge-identity') if args.identity_query else INIT
    if args.battery_monitor:
        init=INIT.replace(b'allow_raw_read=1',b'allow_reads=1 confirmed_device_type=42495').replace(b'lynx-gauge-sample',name.encode()).replace(b'lynx_gauge_sample',name.replace('-','_').encode())
        # Preserve the fixture filename used by this isolated initramfs.
        init=init.replace(('/fixture/'+name+'.ko').encode(),b'/fixture/lynx-gauge-sample.ko')
    put(entries, 'init', init)
    put(entries, 'fixture/lynx-gauge-sample.ko', module, 0o100600)
    out = PORT / 'artifacts' / ('emulated-gauge-sample-' + str(time.time_ns()))
    out.mkdir(mode=0o700)
    (out / 'Image').write_bytes(gzip.decompress(boot['kernel']))
    (out / 'initramfs').write_bytes(pack(entries))
    (out / 'init-source').write_bytes(init)
    q = ROOT / 'tools/qemu/noble/root'
    env = dict(os.environ, LD_LIBRARY_PATH=str(q / 'usr/lib/x86_64-linux-gnu'),
               QEMU_MODULE_DIR=str(q / 'usr/lib/x86_64-linux-gnu/qemu'), TMPDIR=str(out))
    command = [str(q / 'usr/bin/qemu-system-aarch64'), '-L', str(q / 'usr/share/qemu'),
               '-no-user-config', '-nodefaults', '-machine', 'virt,gic-version=3', '-accel', 'tcg',
               '-cpu', 'cortex-a710', '-smp', '2', '-m', '1024', '-display', 'none', '-monitor', 'none',
               '-serial', 'stdio', '-nic', 'none', '-no-reboot', '-kernel', str(out / 'Image'),
               '-initrd', str(out / 'initramfs'), '-append', 'console=ttyAMA0 rdinit=/init loglevel=7 panic=0']
    timeout = False
    try:
        p = subprocess.run(command, env=env, capture_output=True, timeout=50)
        console, rc = p.stdout + p.stderr, p.returncode
    except subprocess.TimeoutExpired as error:
        console, rc, timeout = (error.stdout or b'') + (error.stderr or b''), None, True
    (out / 'console.log').write_bytes(console)
    checks = {name: ('GAUGE_' + name + '=PASS').encode() in console
              for name in ['DEFAULT_REFUSAL', 'DRIVER_REGISTERED', 'UNLOADED']}
    checks.update(clean_poweroff=b'reboot: Power down' in console,
                  no_probe_sample=b'LYNX_GAUGE_RAW register=' not in console and b'LYNX_GAUGE_DEVICE_TYPE word=' not in console,
                  no_panic_or_cfi_failure=not any(x in console for x in [b'Kernel panic', b'CFI failure', b'GAUGE_TEST_FAILURE=']))
    result = {'passed': rc == 0 and not timeout and all(checks.values()), 'checks': checks,
              'module_sha256': digest, 'identity_query_variant': args.identity_query, 'phone_contacted': False, 'physical_gauge_tested': False,
              'i2c_probe_callback_tested': False, 'exit_code': rc, 'timed_out': timeout,
              'limits': 'Stock-kernel VM loader/CFI entry and register/unregister only. Does not prove gauge probe ABI, bus response, temperature accuracy, or physical safety.'}
    (out / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'result': str(out / 'result.json'), **result}, indent=2))
    if not result['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
