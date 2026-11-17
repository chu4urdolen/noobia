"""Prepare separate offline diagnostic artifacts; no USB access or flashing."""
import hashlib
import json
from pathlib import Path
import struct
from image_formats import read_boot_v4, read_newc, require
from ramdisk_codec import compress_legacy, decompress

BASE = Path(__file__).resolve().parent
STOCK = BASE / 'artifacts/stock-cph2493-August-eu-ota'
PROOF = BASE / 'artifacts/busybox-August-boot-proof-bound-guards'
OUTPUT = BASE / 'artifacts/busybox-usb-module-checkpoints'


def pack(entries):
    archive = bytearray()
    trailer = dict(mode=0, uid=0, gid=0, rdevmajor=0, rdevminor=0, data=b'')
    for inode, (name, item) in enumerate([*entries.items(), ('TRAILER!!!', trailer)], 1):
        encoded = name.encode() + b'\0'
        fields = [inode, item['mode'], item['uid'], item['gid'], 1, 0,
                  len(item['data']), 0, 0, item['rdevmajor'], item['rdevminor'], len(encoded), 0]
        archive += b'070701' + ''.join(f'{value:08x}' for value in fields).encode() + encoded
        archive += b'\0' * (-len(archive) % 4)
        archive += item['data']
        archive += b'\0' * (-len(archive) % 4)
    archive += b'\0' * (-len(archive) % 512)
    require(read_newc(archive) == entries, 'CPIO round trip failed')
    return compress_legacy(bytes(archive))


def main():
    require(not OUTPUT.exists(), 'Preserve previous diagnostic artifacts')
    stock = (STOCK / 'boot.img').read_bytes()
    require(hashlib.sha256(stock).hexdigest() == 'a67f03d7b826b834c23653b67eaa6efa971eb70ef8af19eee4d33fb5fc7fe995', 'Stock boot changed')
    source = (PROOF / 'nord3-busybox-candidate.img').read_bytes()
    require(hashlib.sha256(source).hexdigest() == 'a9a72334185a5ddec9b6e3ece6e9e01600582f62c4db7bebc8ce87c4d5c3fe43', 'Proven baseline changed')
    boot = read_boot_v4(source)
    require(boot['kernel'] == read_boot_v4(stock)['kernel'], 'Stock kernel required')
    original = read_newc(decompress(boot['ramdisk']))
    proven_init = original['init']['data']
    require(proven_init == (BASE / 'init-boot-proof').read_bytes(), 'Proof source differs')
    guard = proven_init[proven_init.index(b'wdt_ready=0'):proven_init.index(b'\nif [ "$wdt_ready"')]
    prefix = proven_init[:proven_init.index(b'\nif [ "$wdt_ready"')]
    require(hashlib.sha256(original['bin/boot-proof-reboot']['data']).hexdigest() == 'e07fbe2825b8283f8c58f7f55eaf143fe9d983bd05c7478b659840dff36f8d08', 'Reboot helper changed')
    vendor = read_newc(decompress((STOCK / 'unpacked-vendor-boot/vendor_ramdisk00').read_bytes()))
    audit = json.loads((BASE / 'docs/august-vendor-ramdisk-audit.json').read_text())
    expected = {item['path']: item['sha256'] for item in audit['entries']}
    modules = [name for name in (BASE / 'artifacts/busybox-August-usb-device-xhci/usb-modules.load').read_text().splitlines() if name != 'mtk_wdt.ko']
    require(len(modules) == len(set(modules)) == 34, 'Unexpected USB module list')
    require(modules[-1] == 'mtu3.ko' and modules.index('xhci-mtk-hcd.ko') < modules.index('mtu3.ko'), 'Module order changed')
    combined = {**vendor, **original}
    for name in ['mtk_wdt.ko', 'reboot-mode.ko', 'syscon-reboot-mode.ko', *modules]:
        path = 'lib/modules/' + name
        require(hashlib.sha256(combined[path]['data']).hexdigest() == expected[path], 'Module mismatch: ' + name)
    OUTPUT.mkdir()
    reports = []
    for stage, selected in [('suppliers', modules[:-1]), ('with-mtu3', modules)]:
        folder = OUTPUT / stage
        folder.mkdir()
        entries = {name: dict(item) for name, item in original.items()}
        init = prefix + b'\n[ "$wdt_ready" = 1 ] && [ "$mode_ready" = 1 ] || { log "CHECKPOINT_RESET_GUARD_STOP"; stop; }\n'
        init += (BASE / 'usb-module-checkpoint.sh').read_bytes()
        init += b'\nlynx_load_checkpoint_modules /etc/lynx-checkpoint-modules.load || stop\n'
        init += guard + b'\n[ "$wdt_ready" = 1 ] && [ "$mode_ready" = 1 ] || { log "CHECKPOINT_RESET_GUARD_CHANGED"; stop; }\n'
        init += b'log "CHECKPOINT_ALL_MODULES_LOADED; REQUESTING_ONE_RESTART2_BOOTLOADER"\n/bin/boot-proof-reboot\nlog "REBOOT_RETURNED; NO_RETRY"\nstop\n'
        entries['init']['data'] = init
        entries['etc/lynx-checkpoint-modules.load'] = dict(mode=0o100644, uid=0, gid=0, rdevmajor=0, rdevminor=0, data=('\n'.join(selected) + '\n').encode())
        ramdisk = pack(entries)
        header = bytearray(source[:1584])
        struct.pack_into('<I', header, 12, len(ramdisk))
        align = lambda length: (length + 4095) // 4096 * 4096
        payload = bytes(header).ljust(4096, b'\0') + boot['kernel'].ljust(align(len(boot['kernel'])), b'\0') + ramdisk.ljust(align(len(ramdisk)), b'\0')
        magic, _, _, coverage, offset, _ = struct.unpack('!4sIIQQQ28x', stock[-64:])
        require(magic == b'AVBf' and len(payload) <= coverage <= offset, 'Metadata overlap')
        image = payload.ljust(coverage, b'\0') + stock[coverage:]
        require(len(image) == 67108864, 'Partition size changed')
        require(read_boot_v4(image)['kernel'] == boot['kernel'], 'Kernel altered')
        (folder / 'nord3-busybox-candidate.img').write_bytes(image)
        (folder / 'init-source').write_bytes(init)
        (folder / 'initramfs.cpio.lz4').write_bytes(ramdisk)
        report = dict(stage=stage, candidate_sha256=hashlib.sha256(image).hexdigest(), init_sha256=hashlib.sha256(init).hexdigest(), module_count_including_reset=3 + len(selected), additional_modules=selected,
                      phone_contacted=False, flash_eligible=False, hardware_tested=False,
                      purpose='One guarded software return only after every listed module load succeeds; no USB role or gadget configuration',
                      limits='A missing return cannot distinguish load failure, probe hang, or reset failure. Module insertion does not prove platform binding. Requires independent validation before hardware use.')
        (folder / 'build-validation.json').write_text(json.dumps(report, indent=2) + '\n')
        reports.append(report)
    # Keep the failed console image and all of its exact source untouched.
    console = (BASE / 'init-busybox-usb-console').read_bytes()
    marker = b'log "ACM_GADGET_BOUND $udc"\n'
    require(console.count(marker) == 1, 'Console insertion point changed')
    replacement = marker + (BASE / 'usb-enumeration-check.sh').read_bytes() + b'\nlynx_wait_usb_configured "/sys/class/udc/$udc" || return_fastboot "host did not configure gadget within 30 seconds"\nlog "ACM_HOST_CONFIGURED $udc"\n'
    (OUTPUT / 'init-busybox-usb-console-enumeration-draft').write_bytes(console.replace(marker, replacement))
    (OUTPUT / 'summary.json').write_text(json.dumps(reports, indent=2) + '\n')
    print(json.dumps(reports, indent=2))


if __name__ == '__main__':
    main()
