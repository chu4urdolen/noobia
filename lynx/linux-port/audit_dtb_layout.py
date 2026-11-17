"""Validate stock DTB/DTBO headers and retain observed Fastboot geometry."""
import json
from pathlib import Path
import re
import struct

base = Path(__file__).resolve().parent
stock = base / 'artifacts/stock-cph2493-A10'


def fdt(data):
    prefix = data.find(bytes.fromhex('d00dfeed'))
    assert prefix >= 0, 'No FDT header found; initial bytes: ' + data[:32].hex()
    data = data[prefix:]
    header = struct.unpack_from('>10I', data, 0)
    magic, total, structure, strings, _, version, _, _, strings_size, structure_size = header
    assert magic == 0xd00dfeed and total <= len(data)
    assert structure + structure_size <= total and strings + strings_size <= total
    stack = []
    nodes = {}
    offset = structure
    while offset < structure + structure_size:
        token = struct.unpack_from('>I', data, offset)[0]
        offset += 4
        if token == 1:
            end = data.index(b'\0', offset)
            stack.append(data[offset:end].decode(errors='replace'))
            offset = (end + 4) & ~3
            nodes['/' + '/'.join(stack[1:])] = {}
        elif token == 2:
            stack.pop()
        elif token == 3:
            size, name_offset = struct.unpack_from('>2I', data, offset)
            offset += 8
            end = data.index(b'\0', strings + name_offset)
            name = data[strings + name_offset:end].decode()
            value = data[offset:offset + size]
            path = '/' + '/'.join(stack[1:])
            if name in ('compatible', 'model', 'status', 'dr_mode', 'maximum-speed', 'clock-names', 'phy-names'):
                nodes[path][name] = value.rstrip(b'\0').decode(errors='replace').split('\0')
            elif name in ('reg', 'phys', 'clocks', 'power-domains', 'vusb33-supply', 'phandle', 'linux,phandle'):
                nodes[path][name] = [hex(struct.unpack_from('>I', value, i)[0]) for i in range(0, len(value), 4)]
            offset = (offset + size + 3) & ~3
        elif token == 4:
            pass
        elif token == 9:
            break
        else:
            raise RuntimeError('Unknown FDT token: ' + str(token))
    return {'wrapper_bytes': prefix, 'total_size': total, 'version': version, 'root': nodes.get('/', {}), 'usb_nodes': {k: v for k, v in nodes.items() if ('usb' in k.lower() or 'xsphy' in k.lower()) and v}}


stock_dtb = fdt((stock / 'stock.dtb').read_bytes())
overlay = (stock / 'dtbo.img').read_bytes()
magic, total, header_size, entry_size, count, entries_offset, page_size, version = struct.unpack_from('>8I', overlay, 0)
assert magic == 0xd7b7ab1e and total <= len(overlay) and entry_size >= 32
entries = []
for i in range(count):
    size, offset, identifier, revision, *custom = struct.unpack_from('>8I', overlay, entries_offset + i * entry_size)
    assert offset + size <= total
    tree = fdt(overlay[offset:offset + size])
    entries.append({'index': i, 'id': hex(identifier), 'revision': revision, 'custom': custom, 'size': size, 'dtb_validated': True, 'usb_overrides': tree['usb_nodes']})
observed = Path('/noobia/lynx/logs/fastboot-all-20261009.txt').read_text()
partitions = {name: int(value, 16) for name, value in re.findall(r'partition-size:([^:]+):\s*(?:0x)?([0-9a-fA-F]+)', observed)}
report = {'stock_dtb': stock_dtb, 'stock_dtbo': {'entries': entries, 'page_size': page_size, 'version': version}, 'partition_sizes_bytes_observed_20261009': partitions, 'critical_partitions_not_to_modify': ['preloader', 'preloader_backup', 'lk_a', 'lk_b', 'nvram', 'nvdata', 'persist', 'seccfg', 'efuse'], 'current_device_dtb_readback_available': False}
(base / 'docs/dtb-and-partition-audit.json').write_text(json.dumps(report, indent=2) + '\n')
print('Validated stock DTB:', stock_dtb['total_size'], 'bytes;', len(stock_dtb['usb_nodes']), 'USB-related nodes')
print('Validated DTBO entries:', count)
print('Observed physical partition sizes:', json.dumps(partitions, sort_keys=True))
