"""Verify stock AVB signatures and available payloads without touching the phone."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import argparse

base = Path(__file__).resolve().parent
source = base / 'sources/aosp-avb'
spec = importlib.util.spec_from_file_location('avbtool', source / 'avbtool.py')
avb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(avb)
tool = avb.Avb()
parser = argparse.ArgumentParser()
parser.add_argument('--stock-dir', type=Path, default=base / 'artifacts/stock-cph2493-A10')
parser.add_argument('--manifest', type=Path, default=base / 'docs/stock-component-manifest.json')
parser.add_argument('--report', type=Path, default=base / 'docs/stock-avb-audit.json')
args = parser.parse_args()
for output_path in (args.report.resolve(),):
    if not output_path.is_relative_to(base):
        raise ValueError('Keep audit output inside the Lynx workspace')
stock = args.stock_dir
expected = {Path(item['file']).name: item['sha256'] for item in
            json.loads(args.manifest.read_text())['components']}
images = {}
parsed = {}
for name in ('boot.img', 'vendor_boot.img', 'dtbo.img', 'vbmeta.img', 'vbmeta_system.img', 'vbmeta_vendor.img'):
    path = stock / name
    image = avb.ImageHandler(str(path), read_only=True)
    item = {'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    if item['sha256'] != expected[name]:
        raise ValueError('Stock component changed: ' + name)
    try:
        footer, header, descriptors, _ = tool._parse_image(image)
        blob = tool._load_vbmeta_blob(image)
        key_start = header.SIZE + header.authentication_data_block_size + header.public_key_offset
        key = blob[key_start:key_start + header.public_key_size]
        algorithm, _ = avb.lookup_algorithm_by_type(header.algorithm_type)
        signature_valid = avb.verify_vbmeta_signature(header, blob)
        item.update(algorithm=algorithm,
                    signature_valid_against_embedded_key=signature_valid if key else None,
                    embedded_key_sha256=hashlib.sha256(key).hexdigest() if key else None,
                    metadata_check_passed=signature_valid,
                    rollback_index=header.rollback_index, rollback_index_location=header.rollback_index_location,
                    flags=header.flags)
        parsed[name] = (header, descriptors, key)
        if key:
            damaged = bytearray(blob)
            damaged[header.SIZE + header.signature_offset] ^= 1
            item['corrupted_signature_rejected'] = not avb.verify_vbmeta_signature(header, bytes(damaged))
    except (avb.AvbError, LookupError, ValueError) as error:
        item['avb_metadata_unavailable'] = str(error)
    images[name] = item

checks = []
for image_name, (_, descriptors, _) in parsed.items():
    for descriptor in descriptors:
        if isinstance(descriptor, avb.AvbHashDescriptor):
            target = stock / (descriptor.partition_name + '.img')
            item = {'descriptor_image': image_name, 'partition': descriptor.partition_name,
                    'kind': 'hash', 'image_size': descriptor.image_size}
            if target.exists():
                data = target.read_bytes()
                item['valid'] = len(data) >= descriptor.image_size and bool(descriptor.digest) and (
                    hashlib.new(descriptor.hash_algorithm, descriptor.salt + data[:descriptor.image_size]).digest() == descriptor.digest)
            else:
                item['not_checked'] = 'Payload not extracted'
            checks.append(item)
        elif isinstance(descriptor, avb.AvbChainPartitionDescriptor):
            item = {'descriptor_image': image_name, 'partition': descriptor.partition_name,
                    'kind': 'chain', 'rollback_index_location': descriptor.rollback_index_location}
            child = parsed.get(descriptor.partition_name + '.img')
            item['embedded_child_key_matches'] = child is not None and child[2] == descriptor.public_key
            checks.append(item)
        elif isinstance(descriptor, avb.AvbHashtreeDescriptor):
            checks.append({'descriptor_image': image_name, 'partition': descriptor.partition_name,
                           'kind': 'hashtree', 'not_checked': 'Filesystem payload not extracted'})

report = {'device': 'Lynx / CPH2493',
          'tool_commit': subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip(),
          'images': images, 'descriptor_checks': checks,
          'publisher_key_independently_trusted': False,
          'phone_stored_rollback_indexes_known': False,
          'installed_firmware_compatibility_verified': False,
          'restoration_path_verified': False,
          'flash_eligible': False,
          'limits': ['Embedded-key verification proves internal integrity, not independent OEM authenticity.',
                     'Package rollback indexes do not reveal indexes stored by Lynx.',
                     'Filesystem hashtrees are not validated by this component-only audit.']}
args.report.write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
