"""Offline boot-metadata diagnostic; keep stock metadata, change native data."""
import hashlib
import argparse
import json
from pathlib import Path
import stat
import struct

from image_formats import read_boot_v4, read_newc, require
from ramdisk_codec import compress_legacy, decompress

BASE = Path(__file__).resolve().parent
STOCK = BASE / 'artifacts/stock-cph2493-August-eu-ota'
SOURCE = BASE / 'artifacts/busybox-August-lz4-avb'
SUPPLIERS = BASE / 'artifacts/busybox-August-suppliers'
OUTPUT = BASE / 'artifacts/busybox-August-stock-metadata'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--include-i2c-clock', action='store_true', help='Load the stock IMP IIC clock provider before the I2C bus driver')
    parser.add_argument('--always-usb', action='store_true', help='Use a preserved separate init that establishes watchdog and USB without a custom boot argument')
    parser.add_argument('--usb-device-mode', action='store_true', help='Request peripheral mode through the bound primary MTU3 controller only')
    parser.add_argument('--include-xhci', action='store_true', help='Load the matching stock xHCI driver before MTU3; withhold MTU3 if xHCI did not load')
    args = parser.parse_args()
    require(not args.always_usb or args.include_i2c_clock, 'Unconditional startup variant requires the clock fix')
    require(not args.usb_device_mode or args.always_usb, 'Device role requires unconditional startup')
    require(not args.include_xhci or args.usb_device_mode, 'xHCI variant requires guarded device-mode startup')
    output = BASE / 'artifacts/busybox-August-stock-metadata-clock' if args.include_i2c_clock else OUTPUT
    if args.always_usb:
        output = BASE / 'artifacts/busybox-August-clock-always'
    if args.usb_device_mode:
        output = BASE / 'artifacts/busybox-August-usb-device-mode'
    if args.include_xhci:
        output = BASE / 'artifacts/busybox-August-usb-device-xhci'
    require(not output.exists(), 'Preserve existing diagnostic image')
    stock = (STOCK / 'boot.img').read_bytes()
    require(hashlib.sha256(stock).hexdigest() == 'a67f03d7b826b834c23653b67eaa6efa971eb70ef8af19eee4d33fb5fc7fe995', 'Stock image changed')
    original = (SOURCE / 'nord3-busybox-candidate.img').read_bytes()
    report = json.loads((SOURCE / 'build-validation.json').read_text())
    require(hashlib.sha256(original).hexdigest() == report['candidate_sha256'], 'Native source changed')
    boot = read_boot_v4(original)
    entries = read_newc(decompress(boot['ramdisk']))
    init_source = 'init'
    if args.always_usb:
        init_source = 'init-usb-always'
        original_init = entries['init']['data']
        old_condition = b"if $BB grep -q 'noobia.usb=1' /proc/cmdline; then"
        require(original_init.count(old_condition) == 1, 'Unexpected original USB gate')
        new_init = original_init.replace(old_condition, b'# Watchdog and USB startup must not depend on delivery of a custom boot argument.\nif :; then')
        new_init = new_init.replace(b'log "NORD3_NATIVE_LINUX_PID1_OK pid=$$"', b'log "NORD3_NATIVE_LINUX_PID1_OK pid=$$"\nlog "Actual kernel command line: $($BB cat /proc/cmdline)"')
        if args.usb_device_mode:
            init_source = 'init-usb-device-mode'
            if args.include_xhci:
                init_source = 'init-usb-device-xhci'
            new_init = new_init.replace(b'# Native Linux PID 1. All writes are confined to initramfs, tmpfs and configfs.', b'# Native Linux PID 1. Runtime writes use RAM filesystems and guarded USB sysfs only.')
            helper = (BASE / ('usb-device-mode-xhci.sh' if args.include_xhci else 'usb-device-mode.sh')).read_bytes()
            new_init = new_init.replace(b'# No partition mounting, Android init, HALs, or firmware-flashing tools.', helper + b'\n# No partition mounting, Android init, HALs, or firmware-flashing tools.')
            new_init = new_init.replace(b'    $BB mount -t configfs', b'    lynx_usb_device_mode\n    $BB mount -t configfs')
            new_init = new_init.replace(b'        while [ "$attempts" -lt 15 ]; do', b'        while [ "$attempts" -lt 15 ]; do\n            lynx_usb_device_mode')
            if args.include_xhci:
                new_init = new_init.replace(b'    while IFS= read -r module; do', b'    lynx_xhci_ready=0\n    while IFS= read -r module; do')
                new_init = new_init.replace(b'        [ -n "$module" ] || continue', b'        [ -n "$module" ] || continue\n        if [ "$module" = mtu3.ko ] && [ "$lynx_xhci_ready" != 1 ]; then\n            log "MTU3 withheld: matching xHCI module is unavailable"\n            continue\n        fi')
                new_init = new_init.replace(b'    done < /etc/usb-modules.load', b'        if [ "$module" = xhci-mtk-hcd.ko ] && [ -d /sys/module/xhci_mtk_hcd ]; then\n            lynx_xhci_ready=1\n        fi\n    done < /etc/usb-modules.load')
        source_path = BASE / init_source
        require(not source_path.exists() or source_path.read_bytes() == new_init, 'Preserve existing alternate init source')
        source_path.write_bytes(new_init)
        entries['init']['data'] = new_init
    order = (SUPPLIERS / 'usb-modules.load').read_bytes()
    if args.include_i2c_clock:
        dependency_root = STOCK / 'vendor-ramdisk-unpacked/lib/modules'
        dependencies = {}
        for line in (dependency_root / 'modules.dep').read_text().splitlines():
            name, tail = line.split(':', 1)
            dependencies[Path(name).name] = [Path(value).name for value in tail.split()]
        ordered, active = [], set()

        def add(name):
            if name in ordered:
                return
            require(name not in active, 'Dependency cycle')
            active.add(name)
            for dependency in dependencies[name]:
                add(dependency)
            ordered.append(name)
            active.remove(name)

        source_order = order.decode().splitlines()
        if args.include_xhci:
            source_order.insert(source_order.index('mtu3.ko'), 'xhci-mtk-hcd.ko')
        for name in ['mtk_wdt.ko', 'clk-mt6983.ko', 'clk-mt6983-imp_iic_wrap.ko'] + source_order:
            add(name)
        require(ordered.index('clk-mt6983-imp_iic_wrap.ko') < ordered.index('i2c-mt65xx.ko'), 'Clock must load before I2C')
        if args.include_xhci:
            require(ordered.index('xhci-mtk-hcd.ko') < ordered.index('mtu3.ko'), 'Host driver must load before MTU3 creates its child')
        order = ('\n'.join(ordered) + '\n').encode()
    entries['etc/usb-modules.load']['data'] = order
    archive = bytearray()
    for inode, (name, item) in enumerate([*entries.items(), ('TRAILER!!!', {'mode': 0, 'uid': 0, 'gid': 0, 'rdevmajor': 0, 'rdevminor': 0, 'data': b''})], 1):
        encoded = name.encode() + b'\0'
        fields = [inode, item['mode'], item['uid'], item['gid'], 1, 0, len(item['data']), 0, 0, item['rdevmajor'], item['rdevminor'], len(encoded), 0]
        archive += b'070701' + ''.join(f'{value:08x}' for value in fields).encode() + encoded
        archive += b'\0' * (-len(archive) % 4)
        archive += item['data']
        archive += b'\0' * (-len(archive) % 4)
    archive += b'\0' * (-len(archive) % 512)
    require(read_newc(archive) == entries, 'Archive changed during packing')
    ramdisk = compress_legacy(bytes(archive))
    header = bytearray(original[:1584])
    struct.pack_into('<I', header, 12, len(ramdisk))
    align = lambda value: (value + 4095) // 4096 * 4096
    payload = bytes(header).ljust(4096, b'\0') + boot['kernel'].ljust(align(len(boot['kernel'])), b'\0') + ramdisk.ljust(align(len(ramdisk)), b'\0')
    magic, major, minor, original_size, metadata_offset, metadata_size = struct.unpack('!4sIIQQQ28x', stock[-64:])
    require(magic == b'AVBf' and len(payload) <= original_size <= metadata_offset, 'Native payload overlaps preserved stock metadata')
    image = payload.ljust(original_size, b'\0') + stock[original_size:]
    require(len(image) == len(stock) == 67108864, 'Partition size changed')
    vendor_raw = decompress((STOCK / 'unpacked-vendor-boot/vendor_ramdisk00').read_bytes())
    vendor = read_newc(vendor_raw)
    merged = {**vendor, **entries}
    stock_audit = json.loads((BASE / 'docs/august-vendor-ramdisk-audit.json').read_text())
    require(hashlib.sha256((STOCK / 'unpacked-vendor-boot/vendor_ramdisk00').read_bytes()).hexdigest() == stock_audit['compressed_ramdisk_sha256'], 'Vendor archive changed')
    hashes = {item['path']: item['sha256'] for item in stock_audit['entries']}
    modules = order.decode().splitlines()
    for name in modules:
        path = 'lib/modules/' + name
        require(hashlib.sha256(merged[path]['data']).hexdigest() == hashes[path], 'Module bytes differ from stock')
    output.mkdir()
    (output / 'nord3-busybox-candidate.img').write_bytes(image)
    (output / 'initramfs.cpio.lz4').write_bytes(ramdisk)
    (output / 'usb-modules.load').write_bytes(order)
    report.update(status='Offline stock-metadata diagnostic; native data does not match OEM hash; not hardware-tested',
                  candidate_sha256=hashlib.sha256(image).hexdigest(), image_bytes=len(image),
                  initramfs_sha256=hashlib.sha256(ramdisk).hexdigest(), ramdisk_bytes=len(ramdisk),
                  uncompressed_initramfs_sha256=hashlib.sha256(archive).hexdigest(),
                  uncompressed_initramfs_identical_to_previous_trial=False,
                  usb_module_count=len(modules), usb_module_load_order=modules,
                  avb_algorithm='SHA256_RSA2048', avb_original_image_size=original_size,
                  diagnostic_metadata_mode='preserved-stock-metadata-with-payload-hash-mismatch',
                  preserved_stock_metadata_sha256=hashlib.sha256(stock[metadata_offset:metadata_offset + metadata_size]).hexdigest(),
                  avb_hash_matches_modified_payload=False, oem_metadata_signature_preserved=True,
                  oem_image_approval_claimed=False, oem_signature_present=False,
                  vendor_ramdisk_required_for_module_resolution=True,
                  required_vendor_ramdisk_sha256=hashlib.sha256((STOCK / 'unpacked-vendor-boot/vendor_ramdisk00').read_bytes()).hexdigest(),
                  modules_resolved_from_vendor=[name for name in modules if 'lib/modules/' + name not in entries],
                  unchanged_native_init_sha256=hashlib.sha256(entries['init']['data']).hexdigest(),
                  i2c_clock_provider_included=args.include_i2c_clock,
                  native_init_source=init_source,
                  unconditional_watchdog_and_usb_startup=args.always_usb,
                  primary_usb_device_mode_requested=args.usb_device_mode,
                  xhci_driver_order_and_mtu3_load_guard_included=args.include_xhci,
                  flash_eligible=False, phone_contacted=False)
    if args.always_usb:
        report.pop('unchanged_native_init_sha256', None)
        report['native_init_sha256'] = hashlib.sha256(entries['init']['data']).hexdigest()
        report['init_syntax_checked_by_target_busybox'] = False
        report['init_arm64_validation_pending'] = True
    report.pop('packaging_command', None)
    (output / 'build-validation.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'candidate_sha256': report['candidate_sha256'], 'payload_bytes': len(payload),
                      'stock_hash_coverage_bytes': original_size, 'module_count': len(modules),
                      'modules_from_stock_vendor': report['modules_resolved_from_vendor']}, indent=2))


if __name__ == '__main__':
    main()
