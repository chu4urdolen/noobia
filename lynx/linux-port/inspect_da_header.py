"""Parse the archived download-agent table without loading it into hardware."""
import hashlib
import json
from pathlib import Path
import struct

base = Path(__file__).resolve().parent
data = (base / 'artifacts/service-reference/DA_BR.bin').read_bytes()
if len(data) < 0x6c:
    raise ValueError('Truncated download-agent header')
header = data[:0x68]
count = struct.unpack_from('<I', data, 0x68)[0]
old = data[0x6c + 0xd8:0x6c + 0xd8 + 2] == b'\xda\xda'
entry_size = 0xd8 if old else 0xdc
if count > 1000 or 0x6c + count * entry_size > len(data):
    raise ValueError('Invalid download-agent table size')
entries = []
for index in range(count):
    offset = 0x6c + index * entry_size
    fields = struct.unpack_from('<' + ('8H' if old else '10H'), data, offset)
    item = {'magic': hex(fields[0]), 'hw_code': hex(fields[1]), 'hw_sub_code': hex(fields[2]),
            'hw_version': hex(fields[3]), 'region_count': fields[-1], 'regions': []}
    start = offset + len(fields) * 2
    if start + fields[-1] * 20 > offset + entry_size:
        raise ValueError('Invalid download-agent regions')
    for region in range(fields[-1]):
        buf, length, address, start_offset, signature_length = struct.unpack_from('<5I', data, start + region * 20)
        if buf + length > len(data) or signature_length > length:
            raise ValueError('Truncated download-agent payload')
        item['regions'].append({'file_offset': buf, 'bytes': length, 'load_address': hex(address),
                                'start_offset': start_offset, 'signature_bytes': signature_length})
    entries.append(item)
report = {'loader_sha256': hashlib.sha256(data).hexdigest(), 'header_hex': header.hex(),
          'v6_marker_present': b'MTK_DA_v6' in header, 'old_table_format': old,
          'entries': entries, 'phone_loader_acceptance_verified': False,
          'readback_route_verified': False, 'flash_eligible': False,
          'parser_reference': 'https://github.com/bkerler/mtkclient/blob/main/mtkclient/Library/DA/daconfig.py'}
(base / 'docs/download-agent-audit.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
