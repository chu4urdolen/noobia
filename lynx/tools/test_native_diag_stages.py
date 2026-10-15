"""Execute the unchanged stage logger with ARM64 BusyBox and the stock kernel."""
import gzip
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
P = ROOT / 'linux-port'
sys.path.insert(0, str(P))
from image_formats import read_boot_v4, read_newc
from ramdisk_codec import decompress
from prepare_busybox_diagnostics import pack
from network_userspace import put
from lynx_decode_stages import decode


def main():
    out = P / 'artifacts' / ('emulated-native-diag-stages-' + str(time.time_ns()))
    out.mkdir()
    source = (P / 'lynx-diag-stage.sh').read_bytes()
    reference = (P / 'artifacts/busybox-August-boot-proof-bound-guards/nord3-busybox-candidate.img').read_bytes()
    assert hashlib.sha256(reference).hexdigest() == 'a9a72334185a5ddec9b6e3ece6e9e01600582f62c4db7bebc8ce87c4d5c3fe43'
    boot = read_boot_v4(reference)
    entries = read_newc(decompress(boot['ramdisk']))
    token = '0123456789abcdef0123456789abcdef'
    put(entries, 'etc/lynx/session-token', (token + '\n').encode(), 0o100644)
    init = b'''#!/bin/sh
BB=/bin/busybox
export PATH=/bin:/sbin
$BB mount -t proc proc /proc
$BB mount -t sysfs sysfs /sys
$BB mount -t tmpfs tmpfs /dev
$BB mount -t tmpfs tmpfs /run
$BB mknod -m 600 /dev/console c 5 1
$BB mknod -m 666 /dev/null c 1 3
exec > /dev/console 2>&1
$BB mkdir -p /run/lynx
'''
    init += source + b'''
lynx_diag_init bootstrap || echo DIAG_INIT_FAILED
lynx_diag_emit 16 0 || echo DIAG_EMIT_FAILED
lynx_diag_emit 18 153 || echo DIAG_EMIT_FAILED
lynx_diag_emit 240 153 || echo DIAG_EMIT_FAILED
for args in '65536 0' '-1 0' '1 secret' '08 0'; do
    lynx_diag_emit $args && echo DIAG_INVALID_ACCEPTED
done
echo DIAG_CAPTURE_BEGIN
$BB cat /run/lynx/stages-bootstrap.hex
echo DIAG_CAPTURE_END
$BB stat -c 'DIAG_PERMISSIONS=%a' /run/lynx/stages-bootstrap.hex
lynx_diag_init unexpected && echo DIAG_BAD_OWNER_ACCEPTED
echo DIAG_TEST_FINISHED
$BB poweroff -f
while :; do $BB sleep 60; done
'''
    put(entries, 'init', init)
    (out / 'Image').write_bytes(gzip.decompress(boot['kernel']))
    (out / 'initramfs').write_bytes(pack(entries))
    (out / 'init-source').write_bytes(init)
    runtime = ROOT / 'tools/qemu/noble/root'
    command = [str(runtime / 'usr/bin/qemu-system-aarch64'), '-L', str(runtime / 'usr/share/qemu'),
               '-no-user-config', '-nodefaults', '-machine', 'virt,gic-version=3', '-accel', 'tcg',
               '-cpu', 'cortex-a72', '-smp', '2', '-m', '1024', '-display', 'none', '-monitor', 'none',
               '-serial', 'stdio', '-nic', 'none', '-no-reboot', '-kernel', str(out / 'Image'),
               '-initrd', str(out / 'initramfs'), '-append', 'console=ttyAMA0 rdinit=/init loglevel=7 panic=0']
    env = dict(os.environ, LD_LIBRARY_PATH=str(runtime / 'usr/lib/x86_64-linux-gnu'),
               QEMU_MODULE_DIR=str(runtime / 'usr/lib/x86_64-linux-gnu/qemu'), TMPDIR=str(ROOT / 'tools/mtk-tmp'))
    started = time.monotonic()
    try:
        result = subprocess.run(command, env=env, capture_output=True, timeout=60)
        raw = result.stdout + result.stderr
        exit_code = result.returncode
    except subprocess.TimeoutExpired as error:
        raw = (error.stdout or b'') + (error.stderr or b'')
        exit_code = None
    (out / 'console.log').write_bytes(raw)
    capture = raw.split(b'DIAG_CAPTURE_BEGIN\r\n')[-1].split(b'DIAG_CAPTURE_END')[0]
    decoded = decode(capture, token)
    (out / 'decoded.json').write_text(json.dumps(decoded, indent=2) + '\n')
    assertions = {'three_records': len(decoded['records']) == 3,
                  'checksum_sequence': decoded['complete_sequences_and_checksums'],
                  'statuses': [r['status'] for r in decoded['records']] == [0, 153, 153],
                  'private_permissions': b'DIAG_PERMISSIONS=600' in raw,
                  'invalid_inputs_refused': b'DIAG_INVALID_ACCEPTED' not in raw and b'DIAG_BAD_OWNER_ACCEPTED' not in raw,
                  'no_runtime_error': b'DIAG_INIT_FAILED' not in raw and b'DIAG_EMIT_FAILED' not in raw,
                  'corruption_rejected': not decode(capture.replace(b'0010', b'0011', 1), token)['complete_sequences_and_checksums'],
                  'wrong_session_rejected': not decode(capture, 'f' * 32)['records'],
                  'truncation_detected': not decode(capture.rstrip()[:-10], token)['complete_sequences_and_checksums']}
    passed = exit_code == 0 and all(assertions.values())
    report = {'passed': passed, 'assertions': assertions, 'exit_code': exit_code,
              'elapsed_seconds': time.monotonic() - started, 'phone_contacted': False,
              'logger_sha256': hashlib.sha256(source).hexdigest(),
              'kernel_sha256': hashlib.sha256(boot['kernel']).hexdigest(),
              'limits': 'Real ARM64 shell/stock kernel in QEMU; no physical persistence or log retrieval demonstrated.'}
    (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'passed': passed, 'report': str(out / 'result.json'), 'assertions': assertions}, indent=2))
    assert passed, 'See saved console and decoded records'


if __name__ == '__main__':
    main()
