"""Prepare a separate stock-module supplier variant offline; never flash."""
import hashlib
import json
from pathlib import Path
import stat
import struct
import subprocess

from image_formats import module_metadata, read_boot_v4, read_newc, require
from ramdisk_codec import compress_legacy, decompress

BASE = Path(__file__).resolve().parent
original = BASE / 'artifacts/busybox-August-lz4-avb'
output = BASE / 'artifacts/busybox-August-suppliers'
stock = BASE / 'artifacts/stock-cph2493-August-eu-ota'
require(not output.exists(), 'Preserve existing diagnostic variant')
report = json.loads((original / 'build-validation.json').read_text())
data = (original / 'nord3-busybox-candidate.img').read_bytes()
require(hashlib.sha256(data).hexdigest() == report['candidate_sha256'], 'Tested candidate changed')
boot = read_boot_v4(data)
entries = read_newc(decompress(boot['ramdisk']))
module_root = stock / 'vendor-ramdisk-unpacked/lib/modules'
audit = json.loads((BASE / 'docs/august-vendor-ramdisk-audit.json').read_text())
hashes = {Path(item['path']).name: item['sha256'] for item in audit['entries'] if item['path'].endswith('.ko')}
require(hashlib.sha256((stock / 'vendor_boot.img').read_bytes()).hexdigest() == audit['stock_vendor_boot_sha256'], 'Stock module source changed')
deps = {}
for line in (module_root / 'modules.dep').read_text().splitlines():
    name, tail = line.split(':', 1)
    deps[Path(name).name] = [Path(value).name for value in tail.split()]
old_order = entries['etc/usb-modules.load']['data'].decode().splitlines()
order, active = [], set()


def add_module(name):
    if name in order:
        return
    require(name not in active, 'Module dependency cycle')
    active.add(name)
    for dep in deps[name]:
        add_module(dep)
    blob = (module_root / name).read_bytes()
    require(hashlib.sha256(blob).hexdigest() == hashes[name], 'Stock module hash mismatch: ' + name)
    metadata = module_metadata(blob)
    require(metadata['values']['vermagic'][0].split()[0] == report['stock_kernel_release'] and metadata['has_symbol_versions'], 'Module ABI mismatch')
    path = 'lib/modules/' + name
    if path not in entries:
        entries[path] = {'mode': stat.S_IFREG | 0o644, 'uid': 0, 'gid': 0, 'rdevmajor': 0, 'rdevminor': 0, 'data': blob}
    order.append(name)
    active.remove(name)


# Watchdog takeover is first. Suppliers precede the original USB driver list.
seeds = ['mtk_wdt.ko', 'i2c-mt65xx.ko', 'mt6375.ko', 'mt6375-adc.ko', 'mt6375-charger.ko']
for name in seeds + old_order:
    add_module(name)
entries['etc/usb-modules.load']['data'] = ('\n'.join(order) + '\n').encode()
archive = bytearray()
inventory = []
for inode, (name, item) in enumerate([*entries.items(), ('TRAILER!!!', {'mode': 0, 'uid': 0, 'gid': 0, 'rdevmajor': 0, 'rdevminor': 0, 'data': b''})], 1):
    encoded = name.encode() + b'\0'
    values = [inode, item['mode'], item['uid'], item['gid'], 1, 0, len(item['data']), 0, 0, item['rdevmajor'], item['rdevminor'], len(encoded), 0]
    archive += b'070701' + ''.join(f'{value:08x}' for value in values).encode() + encoded
    archive += b'\0' * (-len(archive) % 4)
    archive += item['data']
    archive += b'\0' * (-len(archive) % 4)
    inventory.append({'path': name, 'mode': oct(item['mode']), 'size': len(item['data']), 'sha256': hashlib.sha256(item['data']).hexdigest()})
archive += b'\0' * (-len(archive) % 512)
require(read_newc(archive) == entries, 'Repacking changed archive entries')
ramdisk = compress_legacy(bytes(archive))
header = bytearray(data[:1584])
struct.pack_into('<I', header, 12, len(ramdisk))
align = lambda value: (value + 4095) // 4096 * 4096
payload = bytes(header).ljust(4096, b'\0') + boot['kernel'].ljust(align(len(boot['kernel'])), b'\0') + ramdisk.ljust(align(len(ramdisk)), b'\0')
output.mkdir()
candidate = output / 'nord3-busybox-candidate.img'
candidate.write_bytes(payload)
command = list(report['packaging_command'])
command[command.index('--image') + 1] = str(candidate)
subprocess.run(command, check=True)
image = candidate.read_bytes()
require(image[:len(payload)] == payload and len(image) == 67108864, 'Footer append changed boot payload')
added = [name for name in order if name not in old_order]
report.update(status='Offline supplier diagnostic variant; not hardware-tested or authorized for flashing',
              candidate_sha256=hashlib.sha256(image).hexdigest(), ramdisk_bytes=len(ramdisk),
              initramfs_sha256=hashlib.sha256(ramdisk).hexdigest(), uncompressed_initramfs_sha256=hashlib.sha256(archive).hexdigest(),
              uncompressed_initramfs_identical_to_previous_trial=False, previous_trial_candidate_sha256=hashlib.sha256(data).hexdigest(),
              usb_module_count=len(order), usb_module_load_order=order, added_stock_modules=added,
              avb_original_image_size=len(payload), packaging_command=command,
              phone_contacted=False, flash_eligible=False, watchdog_hardware_takeover_proven=False)
(output / 'build-validation.json').write_text(json.dumps(report, indent=2) + '\n')
(output / 'initramfs.cpio.lz4').write_bytes(ramdisk)
(output / 'usb-modules.load').write_bytes(entries['etc/usb-modules.load']['data'])
(output / 'initramfs-inventory.json').write_text(json.dumps(inventory, indent=2) + '\n')
print(json.dumps({'candidate_sha256': report['candidate_sha256'], 'added_modules': added, 'module_count': len(order), 'phone_contacted': False}, indent=2))
