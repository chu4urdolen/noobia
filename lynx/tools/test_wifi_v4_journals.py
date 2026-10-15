"""Real ARM64 test of v4 journal ownership and unchanged supervisor control flow."""
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
F = P / 'artifacts/busybox-wifi-ssh-twostage-v4'
sys.path.insert(0, str(P))
from image_formats import read_boot_v4, read_newc, require
from prepare_busybox_diagnostics import pack
from network_userspace import put
from ramdisk_codec import decompress
from lynx_decode_stages import decode


def main():
    out = P / 'artifacts' / ('emulated-wifi-v4-journals-' + str(time.time_ns()))
    out.mkdir(mode=0o700)
    image = (F / 'nord3-busybox-candidate.img').read_bytes()
    require(hashlib.sha256(image).hexdigest() == '0abe578cdc82a8f42b6bd812f3217dcc622f2a980d93e3c3418bc6dadf731af7', 'V4 image changed')
    boot = read_boot_v4(image)
    entries = read_newc(decompress(boot['ramdisk']))
    extra = read_newc(gzip.decompress((F / 'supplement.cpio.gz').read_bytes()))
    frozen = entries['init']['data']
    bootstrap = frozen[frozen.index(b'lynx_wifi_bootstrap_child_unlogged() {'):frozen.index(b'\n. /etc/lynx/diag-stage.sh')]
    require(bootstrap.count(b'/sys/class/block') == 1, 'Discovery fixture boundary')
    put(entries, 'etc/lynx/wifi-runtime.sh', extra['etc/lynx/wifi-runtime.sh']['data'], 0o100644)
    put(entries, 'etc/lynx/host-ip', extra['etc/lynx/host-ip']['data'], 0o100644)
    reset = P / 'artifacts/stock-cph2493-August-eu-ota/vendor-ramdisk-unpacked/lib/modules/reset-ti-syscon.ko'
    put(entries, 'lib/modules/reset-ti-syscon.ko', reset.read_bytes(), 0o100644)
    # Test-only reboot stub is an explicit RAM fixture; never used on the phone.
    put(entries, 'bin/boot-proof-reboot', b'#!/bin/sh\necho LYNX_VM_ONE_FALLBACK_REQUEST\nexit 0\n')
    init = b'''#!/bin/sh
BB=/bin/busybox
export PATH=/bin:/sbin
$BB mount -t proc proc /proc
$BB mount -t sysfs sysfs /sys
$BB mount -t tmpfs tmpfs /dev
$BB mount -t tmpfs tmpfs /run
$BB mknod -m 600 /dev/console c 5 1
$BB mknod -m 666 /dev/null c 1 3
$BB mknod -m 600 /dev/kmsg c 1 11
exec > /dev/console 2>&1
# Avoid interleaving asynchronous printk copies with a journal's serial export.
printf '4\n' > /proc/sys/kernel/printk
$BB mkdir -p /run/lynx /run/fixture/boot
: > /run/lynx/boot.log
printf 'PARTNAME=boot_a\n' > /run/fixture/boot/uevent
$BB insmod /lib/modules/reset-ti-syscon.ko
printf 'LYNX_VM_RESET_MODULE_EXIT=%s\n' "$?"
lynx_plain_log() { printf 'RAW %s\n' "$*" >> /run/lynx/boot.log; }
. /etc/lynx/diag-stage.sh
. /etc/lynx/diag-hooks.sh
lynx_diag_init supervisor && diag_ready=1
log WIFI_TWO_STAGE_BOOTSTRAP_BEGIN
lynx_load_checkpoint_modules() {
    while IFS= read -r module; do
        log "CHECKPOINT_MODULE_BEGIN $module"
        log "CHECKPOINT_MODULE_OK $module"
    done < "$1"
    return 0
}
lynx_read_own_boot_payload() { log BOOT_A_SUPPLEMENT_VERIFIED_AND_EXTRACTED; return 0; }
'''
    init += bootstrap.replace(b'/sys/class/block', b'/run/fixture')
    init += b'''
lynx_wifi_bootstrap
printf 'LYNX_VM_BOOTSTRAP_EXIT=%s\n' "$?"
. /etc/lynx/wifi-runtime.sh
# Deliberate worker failure after two real stage() calls; no radio hardware in VM.
lynx_wifi_worker_unlogged() {
    lynx_stage DHCP
    lynx_stage SSH_READY_WAITING_FOR_PINNED_HOST
    return 134
}
lynx_wifi_supervise
printf 'LYNX_VM_SUPERVISOR_EXIT=%s\n' "$?"
# Losing diagnostics must not change the underlying worker's failure status.
printf 'bad-token\n' > /etc/lynx/session-token
lynx_wifi_worker
printf 'LYNX_VM_BAD_LOG_TOKEN_WORKER_EXIT=%s\n' "$?"
for owner in supervisor bootstrap wifi; do
    printf 'JOURNAL_BEGIN_%s\n' "$owner"
    $BB cat "/run/lynx/stages-$owner.hex"
    printf 'JOURNAL_END_%s\n' "$owner"
done
echo LYNX_VM_JOURNALS_FINISHED
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
        result = subprocess.run(command, env=env, capture_output=True, timeout=45)
        raw, code = result.stdout + result.stderr, result.returncode
    except subprocess.TimeoutExpired as error:
        raw, code = (error.stdout or b'') + (error.stderr or b''), None
    (out / 'console.log').write_bytes(raw)
    token = json.loads((F / 'build-validation.json').read_text())['session_token']
    journals = {}
    for owner in ['supervisor', 'bootstrap', 'wifi']:
        begin, end = ('JOURNAL_BEGIN_' + owner + '\r\n').encode(), ('JOURNAL_END_' + owner).encode()
        capture = raw.split(begin)[-1].split(end)[0]
        (out / (owner + '.hex')).write_bytes(capture)
        journals[owner] = decode(capture, token)
        (out / (owner + '.json')).write_text(json.dumps(journals[owner], indent=2) + '\n')
    checks = {'reset_module_registers': b'LYNX_VM_RESET_MODULE_EXIT=0' in raw,
              'bootstrap_success': b'LYNX_VM_BOOTSTRAP_EXIT=0' in raw,
              'worker_failure_preserved': b'LYNX_VM_SUPERVISOR_EXIT=1' in raw,
              'logger_failure_does_not_mask_worker': b'LYNX_VM_BAD_LOG_TOKEN_WORKER_EXIT=134' in raw,
              'one_fallback': raw.count(b'LYNX_VM_ONE_FALLBACK_REQUEST\r\n') == 1,
              'separate_valid_sequences': all(j['complete_sequences_and_checksums'] for j in journals.values()),
              'bootstrap_has_storage_discovery_and_payload': {17, 18, 19, 20} <= {int(r['stage_hex'], 16) for r in journals['bootstrap']['records']},
              'wifi_exit_status': journals['wifi']['records'][-1]['status'] == 134 if journals['wifi']['records'] else False}
    passed = code == 0 and all(checks.values())
    report = {'passed': passed, 'checks': checks, 'candidate_sha256': hashlib.sha256(image).hexdigest(),
              'logger_sha256': hashlib.sha256(entries['etc/lynx/diag-stage.sh']['data']).hexdigest(),
              'hooks_sha256': hashlib.sha256(entries['etc/lynx/diag-hooks.sh']['data']).hexdigest(),
              'bootstrap_sha256': hashlib.sha256(bootstrap).hexdigest(),
              'wifi_runtime_sha256': hashlib.sha256(extra['etc/lynx/wifi-runtime.sh']['data']).hexdigest(),
              'phone_contacted': False, 'elapsed_seconds': time.monotonic() - started, 'exit_code': code,
              'limits': 'Exact stock kernel and ARM64 shell; synthetic partition discovery/module loading and failed Wi-Fi worker. Actual reset module registration verified, physical binding/persistence/radio not emulated.'}
    (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'passed': passed, 'report': str(out / 'result.json'), 'checks': checks}, indent=2))
    require(passed, 'V4 journal/control integration failed; inspect preserved captures')


if __name__ == '__main__':
    main()
