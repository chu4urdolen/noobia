"""Add structurally valid boot-local AVB metadata to a copy; never flash."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess

from image_formats import read_boot_v4, require

BASE = Path(__file__).resolve().parent
original_dir = BASE / 'artifacts/busybox-August'
output = BASE / 'artifacts/busybox-August-avb'
if output.exists():
    raise ValueError('Preserve existing AVB candidate; refuse to replace it')
report = json.loads((original_dir / 'build-validation.json').read_text())
original = (original_dir / 'nord3-busybox-candidate.img').read_bytes()
require(hashlib.sha256(original).hexdigest() == report['candidate_sha256'], 'Original trial image changed')
source = BASE / 'sources/aosp-avb'
spec = importlib.util.spec_from_file_location('avbtool', source / 'avbtool.py')
avb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(avb)
tool = avb.Avb()
stock = BASE / 'artifacts/stock-cph2493-August-eu-ota/boot.img'
_, stock_header, stock_descriptors, _ = tool._parse_image(avb.ImageHandler(str(stock), read_only=True))
descriptor = next(value for value in stock_descriptors if isinstance(value, avb.AvbHashDescriptor) and value.partition_name == 'boot')
output.mkdir()
candidate_path = output / 'nord3-busybox-candidate.img'
candidate_path.write_bytes(original)
command = ['python3', str(source / 'avbtool.py'), 'add_hash_footer', '--image', str(candidate_path),
           '--partition_name', 'boot', '--partition_size', '67108864', '--algorithm', 'NONE',
           '--hash_algorithm', 'sha256', '--salt', descriptor.salt.hex(),
           '--rollback_index', str(stock_header.rollback_index)]
subprocess.run(command, check=True)
data = candidate_path.read_bytes()
require(len(data) == 67108864 and data[:len(original)] == original, 'Footer preparation changed original payload')
before, after = read_boot_v4(original), read_boot_v4(data)
require(before == after, 'Boot kernel/ramdisk/header changed')
footer, header, descriptors, _ = tool._parse_image(avb.ImageHandler(str(candidate_path), read_only=True))
require(footer is not None and header.algorithm_type == 0 and header.flags == 0, 'Unexpected AVB algorithm or flags')
hash_descriptor = next(value for value in descriptors if isinstance(value, avb.AvbHashDescriptor))
require(hash_descriptor.partition_name == 'boot' and hash_descriptor.image_size == len(original), 'Wrong boot hash descriptor')
require(hashlib.sha256(hash_descriptor.salt + data[:hash_descriptor.image_size]).digest() == hash_descriptor.digest,
        'Self-consistent boot payload hash failed')
for name in ('initramfs.cpio.gz', 'initramfs-inventory.json', 'usb-modules.load', 'busybox-applets.txt', 'setsid-help.txt'):
    shutil.copyfile(original_dir / name, output / name)
old_hash = report['candidate_sha256']
report.update(image_bytes=len(data), candidate_sha256=hashlib.sha256(data).hexdigest(),
              payload_identical_to_previous_trial=True, previous_trial_candidate_sha256=old_hash,
              avb_footer_present=True, avb_algorithm='NONE', avb_flags=header.flags,
              avb_original_image_size=footer.original_image_size,
              avb_vbmeta_offset=footer.vbmeta_offset, avb_vbmeta_size=footer.vbmeta_size,
              avb_boot_hash_descriptor_verified=True, oem_signature_present=False,
              packaging_command=command, phone_contacted=False, flash_eligible=False)
(output / 'build-validation.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({key: value for key, value in report.items() if key != 'usb_module_load_order'}, indent=2))
