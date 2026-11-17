"""Offline compatibility checks for the loader's RAM patch route; no USB calls."""
import hashlib
import json
from pathlib import Path

base = Path(__file__).resolve().parent
audit = json.loads((base / 'docs/download-agent-audit.json').read_text())
data = (base / 'artifacts/service-reference/DA_BR.bin').read_bytes()
if hashlib.sha256(data).hexdigest() != audit['loader_sha256']:
    raise ValueError('Loader source changed')
regions = audit['entries'][0]['regions']
da1 = data[regions[1]['file_offset']:regions[1]['file_offset'] + regions[1]['bytes']]
da2 = data[regions[2]['file_offset']:regions[2]['file_offset'] + regions[2]['bytes']]
markers = [bytes.fromhex('010154e30114a0e3'), bytes.fromhex('0800a852ff0208eb'),
           bytes.fromhex('010150e30114a0e3'), b'2nd DA address is invalid',
           bytes.fromhex('069b4ff0804002a9')]
found = [i for i, marker in enumerate(markers) if marker in da1]
links = []
for label, payload in (('without_signature', da2[:-regions[2]['signature_bytes']]), ('complete', da2)):
    for algorithm in ('md5', 'sha1', 'sha256'):
        digest = hashlib.new(algorithm, payload).digest()
        offset = da1.find(digest)
        if offset >= 0:
            links.append({'payload': label, 'algorithm': algorithm, 'offset_in_da1': offset,
                          'ram_address': hex(regions[1]['load_address'] and int(regions[1]['load_address'], 16) + offset)})
report = {'loader_sha256': audit['loader_sha256'], 'tool_patch_markers_found': found,
          'da2_hash_links_in_da1': links,
          'potential_ram_route': not found and bool(links),
          'hardware_vulnerability_proven': False, 'patched_loader_prepared': False,
          'usb_operations_performed': 0, 'flash_eligible': False,
          'limits': ['Absence of patch markers is not proof that RAM redirection succeeds.',
                    'The upstream generic patch also relaxes erase/write protection; it cannot be treated as a read-only command by itself.',
                    'A controlled probe needs mutation guards, no automatic fallback, and a reviewed exact RAM payload before execution.'],
          'source': 'https://github.com/bkerler/mtkclient/blob/main/mtkclient/Library/Exploit/carbonara.py'}
(base / 'docs/ram-readback-audit.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
