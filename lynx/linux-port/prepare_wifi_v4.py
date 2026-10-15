"""Offline, immutable v4: add the audited reset supplier and per-process logs."""
import gzip
import hashlib
import json
import secrets
import struct
from pathlib import Path
from image_formats import read_boot_v4, read_newc, require
from network_userspace import put
from prepare_busybox_diagnostics import pack
from ramdisk_codec import decompress

P = Path(__file__).resolve().parent
V3 = P / 'artifacts/busybox-wifi-ssh-twostage-v3'
OUT = P / 'artifacts/busybox-wifi-ssh-twostage-v4'


def hooks(modules):
    codebook = {1: 'PID1/reset guards passed', 16: 'base drivers', 17: 'storage drivers',
                18: 'partition discovery', 19: 'own boot_a supplement read', 20: 'supplement extracted',
                32: 'factory calibration', 33: 'radio drivers', 34: 'connectivity chip check',
                35: 'Wi-Fi station power', 36: 'WLAN interface wait', 37: 'WPA association',
                38: 'DHCP', 39: 'SSH ready', 40: 'pinned host confirmed', 240: 'fallback requested',
                254: 'bootstrap child finished', 255: 'Wi-Fi child finished'}
    code = r'''# log() always returns success; diagnostic failure must not alter recovery flow.
lynx_diag_note() {
    case "$*" in
        WIFI_TWO_STAGE_BOOTSTRAP_BEGIN) lynx_diag_emit 1 0 ;;
        BOOTSTRAP_BASE_DRIVERS) lynx_diag_emit 16 0 ;;
        BOOTSTRAP_STORAGE_DRIVERS) lynx_diag_emit 17 0 ;;
        BOOTSTRAP_PARTITION_DISCOVERY) lynx_diag_emit 18 0 ;;
        BOOTSTRAP_READ_OWN_BOOT_A) lynx_diag_emit 19 0 ;;
        BOOT_A_SUPPLEMENT_VERIFIED_AND_EXTRACTED*) lynx_diag_emit 20 0 ;;
        BOOTSTRAP_FAILED\ status=*) lynx_diag_emit 254 "${1##*=}" ;;
        WIFI_WORKER_FAILED\ status=*) lynx_diag_emit 255 "${1##*=}" ;;
        *REQUESTING_ONE_SUPPORTED_BOOTLOADER_REBOOT) lynx_diag_emit 240 0 ;;
        WIFI_STAGE\ FACTORY_CALIBRATION_READONLY) lynx_diag_emit 32 0 ;;
        WIFI_STAGE\ WIFI_DRIVERS) lynx_diag_emit 33 0 ;;
        WIFI_STAGE\ CONNECTIVITY_CHIP_CHECK) lynx_diag_emit 34 0 ;;
        WIFI_STAGE\ WIFI_STATION_POWER_ON) lynx_diag_emit 35 0 ;;
        WIFI_STAGE\ WLAN_INTERFACE_WAIT) lynx_diag_emit 36 0 ;;
        WIFI_STAGE\ WPA_ASSOCIATION_WAIT) lynx_diag_emit 37 0 ;;
        WIFI_STAGE\ DHCP) lynx_diag_emit 38 0 ;;
        WIFI_STAGE\ SSH_READY_WAITING_FOR_PINNED_HOST) lynx_diag_emit 39 0 ;;
        PINNED_HOST_SSH_CONFIRMED*) lynx_diag_emit 40 0 ;;
'''
    for index, name in enumerate(modules, 4096):
        require(all(c.isalnum() or c in '._-' for c in name), 'Unsafe module name')
        codebook[index] = 'module ' + name + ' (status ffff=begin, 0000=ok, 0001=failed)'
        code += f'        "CHECKPOINT_MODULE_BEGIN {name}") lynx_diag_emit {index} 65535 ;;\n'
        code += f'        "CHECKPOINT_MODULE_OK {name}") lynx_diag_emit {index} 0 ;;\n'
        code += f'        "CHECKPOINT_MODULE_FAILED {name}") lynx_diag_emit {index} 1 ;;\n'
    code += '''    esac
    return 0
}
log() {
    lynx_plain_log "$@"
    if [ "${diag_ready:-0}" = 1 ]; then lynx_diag_note "$@"; fi
    return 0
}
lynx_wifi_bootstrap_child() {
    if lynx_diag_init bootstrap; then diag_ready=1; else diag_ready=0; fi
    lynx_wifi_bootstrap_child_unlogged
    diag_child_status=$?
    [ "$diag_ready" != 1 ] || lynx_diag_emit 254 "$diag_child_status"
    return "$diag_child_status"
}
lynx_wifi_worker() {
    if lynx_diag_init wifi; then diag_ready=1; else diag_ready=0; fi
    lynx_wifi_worker_unlogged
    diag_child_status=$?
    [ "$diag_ready" != 1 ] || lynx_diag_emit 255 "$diag_child_status"
    return "$diag_child_status"
}
'''
    return code.encode(), {str(k): v for k, v in codebook.items()}


def main():
    require(not OUT.exists(), 'Keep previous candidates immutable')
    old = (V3 / 'nord3-busybox-candidate.img').read_bytes()
    require(hashlib.sha256(old).hexdigest() == '3a1c2ddacac0c6fdf7e152a2db30add1b1b4fbab881346d6d346faf584abf94c', 'V3 changed')
    previous = json.loads((V3 / 'build-validation.json').read_text())
    supplier = json.loads((P / 'docs/ufs-reset-supplier-audit.json').read_text())
    require(supplier['passed'] and not supplier['imported_symbol_crc_conflicts'], 'Reset audit failed')
    require(hashlib.sha256(Path(supplier['reset_module']).read_bytes()).hexdigest() == supplier['reset_module_sha256'], 'Reset module changed')
    boot = read_boot_v4(old)
    first = read_newc(decompress(boot['ramdisk']))
    extra = read_newc(gzip.decompress((V3 / 'supplement.cpio.gz').read_bytes()))
    storage = first['etc/lynx/bootstrap-storage-modules.load']['data'].decode().splitlines()
    require('reset-ti-syscon.ko' not in storage, 'Reference already changed')
    storage.insert(0, 'reset-ti-syscon.ko')
    put(first, 'etc/lynx/bootstrap-storage-modules.load', ('\n'.join(storage) + '\n').encode(), 0o100644)
    token = secrets.token_hex(16)
    put(first, 'etc/lynx/session-token', (token + '\n').encode(), 0o100644)
    extra.pop('etc/lynx/session-token')
    journal = (P / 'lynx-diag-stage.sh').read_bytes()
    put(first, 'etc/lynx/diag-stage.sh', journal, 0o100644)
    modules = previous['base_modules'] + storage + previous['radio_modules']
    require(len(set(modules)) == len(modules) and 'mtu3.ko' not in modules, 'Module boundary changed')
    hook, codebook = hooks(modules)
    put(first, 'etc/lynx/diag-hooks.sh', hook, 0o100644)
    put(first, 'etc/lynx/diag-codebook.json', (json.dumps(codebook, indent=2) + '\n').encode(), 0o100644)
    runtime = extra['etc/lynx/wifi-runtime.sh']['data']
    require(runtime.count(b'lynx_wifi_worker() {') == 1, 'Wi-Fi wrapper boundary changed')
    runtime = runtime.replace(b'lynx_wifi_worker() {', b'lynx_wifi_worker_unlogged() {', 1)
    put(extra, 'etc/lynx/wifi-runtime.sh', runtime, 0o100644)
    init = first['init']['data']
    require(init.count(b'log() {') == 2, 'Log boundaries changed')
    # Preserve the initial boot guard logger; wrap only the later RAM logger.
    position = init.index(b'log() {', init.index(b'log() {') + 1)
    init = init[:position] + init[position:].replace(b'log() {', b'lynx_plain_log() {', 1)
    require(init.count(b'lynx_wifi_bootstrap_child() {') == 1, 'Bootstrap boundary changed')
    init = init.replace(b'lynx_wifi_bootstrap_child() {', b'lynx_wifi_bootstrap_child_unlogged() {', 1)
    init = init.replace(b'    boot_seen=0\n', b"    log 'BOOTSTRAP_PARTITION_DISCOVERY'\n    boot_seen=0\n", 1)
    marker = b"\nlog 'WIFI_TWO_STAGE_BOOTSTRAP_BEGIN'\n"
    require(init.count(marker) == 1, 'Prelude boundary changed')
    initialize = b"\n. /etc/lynx/diag-stage.sh || stop\n. /etc/lynx/diag-hooks.sh || stop\nif lynx_diag_init supervisor; then diag_ready=1; else diag_ready=0; fi\n"
    init = init.replace(marker, initialize + marker, 1)
    put(first, 'init', init)
    payload = gzip.compress(decompress(pack(extra)), compresslevel=9, mtime=0)
    payload_sha = hashlib.sha256(payload).hexdigest()
    put(first, 'etc/lynx/payload-bytes', (str(len(payload)) + '\n').encode(), 0o100644)
    put(first, 'etc/lynx/payload-sha256', (payload_sha + '\n').encode(), 0o100644)
    ramdisk = pack(first)
    align = lambda n: (n + 4095) // 4096 * 4096
    header = bytearray(old[:1584])
    struct.pack_into('<I', header, 12, len(ramdisk))
    loaded = bytes(header).ljust(4096, b'\0') + boot['kernel'].ljust(align(len(boot['kernel'])), b'\0') + ramdisk.ljust(align(len(ramdisk)), b'\0')
    _, _, _, coverage, offset, metadata_size = struct.unpack('!4sIIQQQ28x', old[-64:])
    require(len(loaded) <= coverage <= offset, 'First stage exceeds original loaded area')
    reference = (P / 'artifacts/busybox-usb-module-checkpoints/suppliers/nord3-busybox-candidate.img').read_bytes()
    require(hashlib.sha256(reference).hexdigest() == '0208f76c1ef5d7e523dbf83226c208f0a0d8f2c08768cbbdfb79025275fd9ece', 'Baseline changed')
    image = bytearray(loaded.ljust(coverage, b'\0') + reference[coverage:])
    start = 24 * 1024 * 1024
    require(offset + metadata_size <= start and start + len(payload) < len(image) - 64, 'Supplement overlap')
    require(not any(reference[start:start + len(payload)]), 'Nonzero padding replaced')
    image[start:start + len(payload)] = payload
    image = bytes(image)
    require(len(image) == 67108864 and read_boot_v4(image)['kernel'] == boot['kernel'], 'Kernel/geometry changed')
    require(image[offset:offset + metadata_size] == old[offset:offset + metadata_size] and image[-64:] == old[-64:], 'OEM metadata/footer changed')
    require(read_newc(decompress(read_boot_v4(image)['ramdisk'])) == first, 'Bootstrap round trip')
    require(read_newc(gzip.decompress(image[start:start + len(payload)])) == extra, 'Supplement round trip')
    OUT.mkdir(mode=0o700)
    for name, raw in [('nord3-busybox-candidate.img', image), ('supplement.cpio.gz', payload),
                      ('init-source', init), ('initramfs.cpio.lz4', ramdisk), ('diag-hooks.sh', hook),
                      ('wifi-runtime.sh', runtime)]:
        target = OUT / name
        target.write_bytes(raw)
        target.chmod(0o600)
    report = {**previous, 'candidate': str(OUT / 'nord3-busybox-candidate.img'),
              'candidate_sha256': hashlib.sha256(image).hexdigest(), 'init_sha256': hashlib.sha256(init).hexdigest(),
              'ramdisk_bytes': len(ramdisk), 'supplement_bytes': len(payload), 'supplement_sha256': payload_sha,
              'supplement_entry_names': list(extra), 'storage_modules': storage, 'session_token': token,
              'diagnostic_logger_sha256': hashlib.sha256(journal).hexdigest(), 'diagnostic_hooks_sha256': hashlib.sha256(hook).hexdigest(),
              'diagnostic_codebook': codebook, 'reset_supplier_audit': str(P / 'docs/ufs-reset-supplier-audit.json'),
              'phone_contacted': False, 'hardware_wifi_verified': False, 'flash_eligible': False,
              'limits': ['Not independently validated or flashed.', 'RAM/pmsg logging retrieval and physical persistence remain unverified.',
                         'Reset supplier omission fixed; hardware UFS/radio initialization remains unproven.']}
    (OUT / 'build-validation.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: report[k] for k in ['candidate', 'candidate_sha256', 'ramdisk_bytes', 'supplement_bytes', 'storage_modules']}, indent=2))


if __name__ == '__main__':
    main()
