"""Execute extracted original/guarded ARM64 fragments under stock-kernel QEMU."""
import gzip
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import time
from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM

ROOT = Path(__file__).resolve().parent.parent
PROJECT = ROOT / 'linux-port'
sys.path.insert(0, str(PROJECT))
from image_formats import read_boot_v4, read_newc, require
from ramdisk_codec import decompress
from prepare_busybox_diagnostics import pack


def main():
    folder = PROJECT / 'artifacts/mtu3-null-child-guard'
    manifest = json.loads((folder / 'manifest.json').read_text())
    original = Path(manifest['stock_file']).read_bytes()
    modified = (folder / 'mtu3.ko').read_bytes()
    require(hashlib.sha256(original).hexdigest() == manifest['stock_sha256'], 'Original module changed')
    require(hashlib.sha256(modified).hexdigest() == manifest['modified_sha256'], 'Guarded module changed')
    offset = manifest['file_offset']
    before = original[offset:offset + 24]
    after = modified[offset:offset + 24]
    decoder = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
    disassembly = {}
    for name, code in [('original', before), ('guarded', after)]:
        disassembly[name] = [dict(address=hex(i.address), mnemonic=i.mnemonic, operands=i.op_str) for i in decoder.disasm(code, 0x54d0)]
        require(len(disassembly[name]) == 6, 'Unexpected instruction count')
    require(disassembly['guarded'][0]['operands'] == 'x8, [x0, #0x98]', 'Unexpected driver load')
    require(disassembly['guarded'][2]['mnemonic'] == 'cbz' and disassembly['guarded'][2]['operands'] == 'x8, #0x54e4', 'Unexpected guard target')
    output = PROJECT / 'artifacts' / ('emulated-mtu3-null-guard-' + str(time.time_ns()))
    output.mkdir()
    # The existing final branch enters unmodified host-function stack cleanup.
    # In this fragment harness only, substitute RET for that final branch.
    def fragment(name, code):
        words = list(struct.unpack('<6I', code))
        require(words[-1] == 0x17ffffb6, 'Unexpected cleanup branch')
        words[-1] = 0xd65f03c0
        return name + ':\n' + '\n'.join('    .inst ' + hex(word) for word in words) + '\n'
    cases = [('original_null', 'original_fragment', 0, 0, (1 << 64) - 40),
             ('original_bound', 'original_fragment', 0x12345000, 0, 0x12344fd8),
             ('guarded_null', 'guarded_fragment', 0, 0, 0),
             ('guarded_null_preserves', 'guarded_fragment', 0, 0xa5, 0xa5),
             ('guarded_bound', 'guarded_fragment', 0x12345000, 0, 0x12344fd8),
             ('guarded_high_pointer', 'guarded_fragment', 0xffff000000100000, 0, 0xffff0000000fffd8)]
    assembly = '.text\n.global _start\n_start:\n'
    for name, target, driver, initial, expected in cases:
        assembly += f'''    ldr x0, =pdev_fixture
    ldr x19, =ssusb_fixture
    ldr x9, ={hex(driver)}
    str x9, [x0, #152]
    ldr x9, ={hex(initial)}
    str x9, [x19, #376]
    bl {target}
    cbnz w0, failed
    ldr x8, [x19, #376]
    ldr x9, ={hex(expected)}
    cmp x8, x9
    b.ne failed
'''
    assembly += '''    mov x0, #1
    ldr x1, =pass_message
    mov x2, #pass_size
    mov x8, #64
    svc #0
    b poweroff
failed:
    mov x0, #1
    ldr x1, =fail_message
    mov x2, #fail_size
    mov x8, #64
    svc #0
poweroff:
    ldr x0, =0xfee1dead
    ldr x1, =0x28121969
    ldr x2, =0x4321fedc
    mov x3, #0
    mov x8, #142
    svc #0
hold:
    b hold
'''
    assembly += fragment('original_fragment', before) + fragment('guarded_fragment', after)
    assembly += '''.section .rodata
pass_message: .ascii "LYNX_MTU3_GUARD_SIX_CASES_PASS\\n"
.equ pass_size, .-pass_message
fail_message: .ascii "LYNX_MTU3_GUARD_CASE_FAIL\\n"
.equ fail_size, .-fail_message
.bss
.balign 16
pdev_fixture: .skip 256
ssusb_fixture: .skip 512
'''
    source = output / 'test.S'
    source.write_text(assembly)
    gcc = ROOT / 'tools/aarch64-gcc/root'
    compiler = [str(gcc / 'usr/bin/aarch64-linux-gnu-gcc-13'), '-nostdlib', '-static', '-fno-pie', '-no-pie', '-Wl,--build-id=none', '-Wl,-e,_start', str(source), '-o', str(output / 'test.elf')]
    built = subprocess.run(compiler, env=dict(os.environ, LD_LIBRARY_PATH=str(gcc / 'usr/lib/x86_64-linux-gnu')), capture_output=True, timeout=30)
    (output / 'compiler.log').write_bytes(built.stdout + built.stderr)
    require(built.returncode == 0, 'Harness compilation failed; see compiler.log')
    stock = PROJECT / 'artifacts/stock-cph2493-August-eu-ota'
    boot = read_boot_v4((stock / 'boot.img').read_bytes())
    require(hashlib.sha256(boot['kernel']).hexdigest() == 'cbc9f5dc54b5198ddd1e82d5d7bde96f43cbb383a663726ddd68919b0639d3af', 'Stock kernel changed')
    reference = (PROJECT / 'artifacts/busybox-August-boot-proof-bound-guards/nord3-busybox-candidate.img').read_bytes()
    require(hashlib.sha256(reference).hexdigest() == 'a9a72334185a5ddec9b6e3ece6e9e01600582f62c4db7bebc8ce87c4d5c3fe43', 'Minimal reference changed')
    entries = read_newc(decompress(read_boot_v4(reference)['ramdisk']))
    entries['init']['data'] = b'''#!/bin/sh
BB=/bin/busybox
$BB mount -t proc proc /proc
$BB mount -t sysfs sysfs /sys
$BB mount -t tmpfs tmpfs /dev
$BB mknod -m 600 /dev/console c 5 1
exec > /dev/console 2>&1
if $BB insmod /lib/modules/mtu3-original.ko && $BB rmmod mtu3 && $BB insmod /lib/modules/mtu3-guarded.ko; then
    printf 'LYNX_MTU3_MODULE_LOAD_PASS\\n'
else
    printf 'LYNX_MTU3_MODULE_LOAD_FAIL\\n'
fi
exec /bin/mtu3-guard-test
'''
    busybox = (PROJECT / 'artifacts/busybox-aarch64-static').read_bytes()
    for name, code in [('bin/busybox', busybox), ('bin/mtu3-guard-test', (output / 'test.elf').read_bytes())]:
        entries[name] = dict(mode=0o100755, uid=0, gid=0, rdevmajor=0, rdevminor=0, data=code)
    for name, code in [('lib/modules/mtu3-original.ko', original), ('lib/modules/mtu3-guarded.ko', modified)]:
        entries[name] = dict(mode=0o100644, uid=0, gid=0, rdevmajor=0, rdevminor=0, data=code)
    # The stock init normally uses Android's shell: ensure /bin/sh is BusyBox.
    entries['bin/sh'] = dict(mode=0o120777, uid=0, gid=0, rdevmajor=0, rdevminor=0, data=b'/bin/busybox')
    (output / 'Image').write_bytes(gzip.decompress(boot['kernel']))
    (output / 'initramfs').write_bytes((stock / 'unpacked-vendor-boot/vendor_ramdisk00').read_bytes() + pack(entries))
    runtime = ROOT / 'tools/qemu/noble/root'
    command = [str(runtime / 'usr/bin/qemu-system-aarch64'), '-L', str(runtime / 'usr/share/qemu'), '-no-user-config', '-nodefaults', '-machine', 'virt,gic-version=3', '-accel', 'tcg', '-cpu', 'cortex-a72', '-smp', '2', '-m', '1024', '-display', 'none', '-monitor', 'none', '-serial', 'stdio', '-nic', 'none', '-no-reboot', '-kernel', str(output / 'Image'), '-initrd', str(output / 'initramfs'), '-append', 'console=ttyAMA0 rdinit=/init loglevel=7 panic=0']
    env = dict(os.environ, LD_LIBRARY_PATH=str(runtime / 'usr/lib/x86_64-linux-gnu'), QEMU_MODULE_DIR=str(runtime / 'usr/lib/x86_64-linux-gnu/qemu'), TMPDIR=str(ROOT / 'tools/mtk-tmp'))
    started = time.monotonic()
    try:
        process = subprocess.run(command, env=env, capture_output=True, timeout=25)
        raw = process.stdout + process.stderr
        code = process.returncode
        timed_out = False
    except subprocess.TimeoutExpired as error:
        raw = (error.stdout or b'') + (error.stderr or b'')
        code = None
        timed_out = True
    (output / 'console.log').write_bytes(raw)
    module_load_passed = b'LYNX_MTU3_MODULE_LOAD_PASS' in raw and b'LYNX_MTU3_MODULE_LOAD_FAIL' not in raw
    passed = b'LYNX_MTU3_GUARD_SIX_CASES_PASS' in raw and b'LYNX_MTU3_GUARD_CASE_FAIL' not in raw and code == 0 and module_load_passed
    report = dict(passed=passed, stock_and_guarded_module_load_passed=module_load_passed, phone_contacted=False, cases=cases, disassembly=disassembly, modified_module_sha256=manifest['modified_sha256'], compiler=compiler, qemu_command=command, elapsed_seconds=time.monotonic()-started, exit_code=code, timed_out=timed_out, source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(), console_sha256=hashlib.sha256(raw).hexdigest(), limits='Loads original module, unloads it, loads guarded module under exact stock kernel, and executes extracted instruction fragments. Final cleanup branch is RET only in harness. Does not emulate MT6983 probing, hardware binding, or concurrency.')
    (output / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(passed=passed, report=str(output / 'result.json')), indent=2))
    require(passed, 'ARM64 guard execution test failed')


if __name__ == '__main__':
    main()
