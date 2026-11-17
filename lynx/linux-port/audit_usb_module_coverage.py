"""Offline stock USB dependency coverage, including drivers without OF aliases."""
import hashlib
import json
from pathlib import Path

from audit_early_boot import read_fdt, strings

BASE = Path(__file__).resolve().parent
STOCK = BASE / 'artifacts/stock-cph2493-August-eu-ota'
ORDER = BASE / 'artifacts/busybox-August-usb-device-mode/usb-modules.load'
selected = set(ORDER.read_text().splitlines())
nodes, _ = read_fdt((STOCK / 'unpacked-vendor-boot/dtb').read_bytes())
previous = json.loads((BASE / 'docs/early-boot-supplier-audit.json').read_text())
paths = set(previous['nodes'])
paths.update(path for path in nodes if path.startswith('/soc/usb0@11201000/'))
modules = {path.name: path.read_bytes() for path in (STOCK / 'vendor-ramdisk-unpacked/lib/modules').glob('*.ko')}
records = []
for path in sorted(paths):
    props = nodes[path]
    compatible = [value for value in strings(props.get('compatible', b'')) if value.startswith('mediatek,')]
    candidates = sorted(name for name, data in modules.items()
                        if any(value.encode() + b'\0' in data for value in compatible))
    missing = [name for name in candidates if name not in selected]
    records.append({'node': path, 'compatible': compatible, 'status': strings(props.get('status', b'okay\0')),
                    'stock_modules_containing_compatible': candidates,
                    'candidates_not_loaded': missing})
report = {'candidate_load_order_sha256': hashlib.sha256(ORDER.read_bytes()).hexdigest(),
          'module_count': len(selected), 'nodes': records,
          'xhci_module_candidates': [name for name in modules if 'xhci' in name],
          'xhci_modules_not_loaded': [name for name in modules if 'xhci' in name and name not in selected],
          'phone_contacted': False,
          'limits': ['Compatible string presence is a review lead, not proof of a registered driver or required module.',
                     'This uses the stock base DTB and prior supplier closure; actual DTBO selection is unobserved.']}
(BASE / 'docs/usb-module-coverage-audit.json').write_text(json.dumps(report, indent=2) + '\n')
for item in records:
    if item['candidates_not_loaded']:
        print(item['node'], item['status'], item['candidates_not_loaded'])
print('Unloaded xHCI candidates:', report['xhci_modules_not_loaded'])
