"""Extract hash-verified boot-chain references from the working remote full OTA."""
import base64
import hashlib
import json
from pathlib import Path
import re
import zipfile

from inspect_remote_ota import RemoteRange
from ota_payload import parse_header, parse_manifest, reconstruct

BASE = Path(__file__).resolve().parent
OUTPUT = BASE / 'artifacts/stock-cph2493-August-eu-ota'
report = json.loads((OUTPUT / 'remote-inspection.json').read_text())
properties = dict(line.split('=', 1) for line in (OUTPUT / 'payload_properties.txt').read_text().splitlines())
stream = RemoteRange(report['url'])
with zipfile.ZipFile(stream) as archive:
    info = archive.getinfo('payload.bin')
    if info.compress_type != 0 or info.file_size != int(properties['FILE_SIZE']):
        raise ValueError('Expected stored payload of declared size')
    stream.seek(info.header_offset)
    header = stream.read(30)
    if header[:4] != b'PK\x03\x04':
        raise ValueError('Invalid ZIP payload local header')
    import struct
    name_length, extra_length = struct.unpack_from('<HH', header, 26)
    payload_offset = info.header_offset + 30 + name_length + extra_length
    certificate = archive.read('META-INF/com/android/otacert')
    (OUTPUT / 'otacert.pem').write_bytes(certificate)

manifest_size, signature_size = parse_header(stream.fetch(payload_offset, 24))
metadata_size = 24 + manifest_size
if metadata_size != int(properties['METADATA_SIZE']):
    raise ValueError('Metadata size differs from properties')
metadata = stream.fetch(payload_offset, metadata_size)
if hashlib.sha256(metadata).digest() != base64.b64decode(properties['METADATA_HASH'], validate=True):
    raise ValueError('Payload metadata hash mismatch')
(OUTPUT / 'payload-metadata.bin').write_bytes(metadata)
(OUTPUT / 'payload-metadata-signatures.bin').write_bytes(stream.fetch(payload_offset + metadata_size, signature_size))
block_size, partitions = parse_manifest(metadata[24:])
summary = {name: {'bytes': value['size'], 'sha256': value['hash'].hex(),
                  'operations': len(value['operations']),
                  'manifest_minor_version': value['manifest_minor_version'],
                  'old_partition_info_present': value['old_partition_info_present']}
           for name, value in partitions.items()}
(OUTPUT / 'payload-partitions.json').write_text(json.dumps(summary, indent=2) + '\n')
print('Full payload partitions:', ', '.join(partitions), flush=True)
data_base = payload_offset + metadata_size + signature_size


def fetch_blob(offset, length):
    if offset < 0 or data_base + offset + length > payload_offset + info.file_size:
        raise ValueError('Operation exceeds payload bounds')
    return b''.join(stream.fetch(data_base + offset + done, min(8 * 1024 * 1024, length - done))
                    for done in range(0, length, 8 * 1024 * 1024))


components = []
for name in ('lk', 'boot', 'vendor_boot', 'dtbo', 'vbmeta', 'vbmeta_system', 'vbmeta_vendor'):
    if name not in partitions:
        raise ValueError('Missing required boot-chain partition: ' + name)
    data = reconstruct(partitions[name], block_size, fetch_blob)
    path = OUTPUT / (name + '.img')
    path.write_bytes(data)
    components.append({'file': str(path), 'bytes': len(data),
                       'sha256': hashlib.sha256(data).hexdigest(),
                       'payload_operation_hashes_verified': True,
                       'payload_partition_hash_verified': True,
                       'origin': 'Manufacturer-hosted OTA reference; not read back from Lynx'})
    print('Verified and extracted', name, len(data), flush=True)

lk = (OUTPUT / 'lk.img').read_bytes()
builds = sorted(set(match.group().decode() for match in re.finditer(rb'[0-9a-f]{7,40}_\d{12}', lk)))
phone_log = (BASE.parent / 'logs/fastboot-all-20261009.txt').read_text()
installed = re.search(r'version-bootloader:\s*(\S+)', phone_log).group(1)
result = {'url': report['url'], 'stock_version': 'CPH2493_13.1.0.561(EX01)',
          'metadata_hash_verified_against_properties': True, 'components': components,
          'lk_build_strings': builds, 'installed_bootloader': installed,
          'reference_lk_build_string_matches_installed': any(installed.endswith(build) for build in builds),
          'transferred_bytes': stream.transferred,
          'whole_archive_integrity_verified': False, 'ota_signature_verified': False,
          'phone_contacted': False, 'restoration_path_verified': False, 'flash_eligible': False}
(OUTPUT / 'package-inspection.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result, indent=2))
