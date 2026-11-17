"""Match stock ramdisk compression and add boot-local AVB metadata offline."""
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess

from image_formats import read_boot_v4, read_newc, require
from ramdisk_codec import MAGIC, compress_legacy, decompress

BASE = Path(__file__).resolve().parent
stock = BASE / 'artifacts/stock-cph2493-August-eu-ota'
original_dir = BASE / 'artifacts/busybox-August'
output = BASE / 'artifacts/busybox-August-lz4-avb'
require(not output.exists(), 'Preserve existing LZ4 candidate; refuse to overwrite')
original = (original_dir / 'nord3-busybox-candidate.img').read_bytes()
report = json.loads((original_dir / 'build-validation.json').read_text())
require(hashlib.sha256(original).hexdigest() == report['candidate_sha256'], 'Original image changed')
require((stock / 'unpacked-boot/ramdisk').read_bytes().startswith(MAGIC), 'Stock generic compression is not legacy LZ4')
require((stock / 'unpacked-vendor-boot/vendor_ramdisk00').read_bytes().startswith(MAGIC), 'Stock vendor compression is not legacy LZ4')
old = read_boot_v4(original)
raw = gzip.decompress(old['ramdisk'])
ramdisk = compress_legacy(raw)
require(read_newc(decompress(ramdisk)) == read_newc(raw), 'Ramdisk entries changed')
header = bytearray(original[:1584])
struct.pack_into('<I', header, 12, len(ramdisk))
align = lambda value: (value + 4095) // 4096 * 4096
payload = bytes(header).ljust(4096, b'\0') + old['kernel'].ljust(align(len(old['kernel'])), b'\0') + ramdisk.ljust(align(len(ramdisk)), b'\0')
output.mkdir()
candidate = output / 'nord3-busybox-candidate.img'
candidate.write_bytes(payload)
footer_report = json.loads((BASE / 'artifacts/busybox-August-avb/build-validation.json').read_text())
command = list(footer_report['packaging_command'])
command[command.index('--image') + 1] = str(candidate)
subprocess.run(command, check=True)
data = candidate.read_bytes()
require(data[:len(payload)] == payload and len(data) == 67108864, 'AVB append changed boot payload')
new = read_boot_v4(data)
require(new['kernel'] == old['kernel'] and decompress(new['ramdisk']) == raw, 'Kernel or initramfs content changed')
(output / 'initramfs.cpio.lz4').write_bytes(ramdisk)
for name in ('initramfs-inventory.json', 'usb-modules.load', 'busybox-applets.txt', 'setsid-help.txt'):
    shutil.copyfile(original_dir / name, output / name)
report.update(candidate_sha256=hashlib.sha256(data).hexdigest(), image_bytes=len(data), ramdisk_bytes=len(ramdisk),
              initramfs_sha256=hashlib.sha256(ramdisk).hexdigest(), ramdisk_compression='legacy-lz4',
              uncompressed_initramfs_identical_to_previous_trial=True, uncompressed_initramfs_sha256=hashlib.sha256(raw).hexdigest(),
              previous_trial_candidate_sha256=report['candidate_sha256'], avb_footer_present=True,
              avb_algorithm='NONE', avb_flags=0, avb_original_image_size=len(payload),
              oem_signature_present=False, phone_contacted=False, flash_eligible=False,
              packaging_command=command)
(output / 'build-validation.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({key: value for key, value in report.items() if key != 'usb_module_load_order'}, indent=2))
