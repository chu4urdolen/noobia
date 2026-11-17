"""Read-only audit of stock FDT suppliers and native module coverage; no USB."""
import hashlib
import json
from pathlib import Path
import struct

from image_formats import module_metadata, read_boot_v4, require

BASE = Path(__file__).resolve().parent
STOCK = BASE / 'artifacts/stock-cph2493-August-eu-ota'
CANDIDATE = BASE / 'artifacts/busybox-August-lz4-avb'


def read_fdt(raw):
    prefix = raw.find(bytes.fromhex('d00dfeed'))
    require(prefix >= 0, 'Missing stock FDT')
    data = raw[prefix:]
    magic, total, start, strings, _, version, _, _, strings_size, size = struct.unpack_from('>10I', data)
    require(total <= len(data) and start + size <= total and strings + strings_size <= total, 'FDT out of bounds')
    nodes, stack, offset = {}, [], start
    while offset < start + size:
        token = struct.unpack_from('>I', data, offset)[0]
        offset += 4
        if token == 1:
            end = data.index(b'\0', offset, start + size)
            stack.append(data[offset:end].decode())
            offset = (end + 4) & ~3
            nodes['/' + '/'.join(stack[1:])] = {}
        elif token == 2:
            stack.pop()
        elif token == 3:
            length, name_offset = struct.unpack_from('>2I', data, offset)
            offset += 8
            require(name_offset < strings_size and offset + length <= start + size, 'FDT property out of bounds')
            end = data.index(b'\0', strings + name_offset, strings + strings_size)
            name = data[strings + name_offset:end].decode()
            nodes['/' + '/'.join(stack[1:])][name] = data[offset:offset + length]
            offset = (offset + length + 3) & ~3
        elif token == 4:
            continue
        elif token == 9:
            return nodes, {'wrapper_bytes': prefix, 'fdt_bytes': total, 'version': version}
        else:
            raise ValueError('Unknown FDT token')
    raise ValueError('Missing FDT end token')


def cells(value):
    require(len(value) % 4 == 0, 'Malformed FDT cells')
    return list(struct.unpack('>' + 'I' * (len(value) // 4), value))


def strings(value):
    return value.rstrip(b'\0').decode(errors='replace').split('\0') if value else []


def main():
    raw = (STOCK / 'unpacked-vendor-boot/dtb').read_bytes()
    nodes, info = read_fdt(raw)
    phandles = {}
    for path, props in nodes.items():
        for key in ('phandle', 'linux,phandle'):
            if key in props:
                phandles[cells(props[key])[0]] = path
    module_root = STOCK / 'vendor-ramdisk-unpacked/lib/modules'
    aliases = {}
    for path in sorted(module_root.glob('*.ko')):
        values = module_metadata(path.read_bytes())['values']
        for alias in values.get('alias', []):
            if alias.startswith('of:') and 'C' in alias:
                aliases.setdefault(alias.split('C', 1)[1].rstrip('*'), set()).add(path.name)
    selected = set((CANDIDATE / 'usb-modules.load').read_text().splitlines())
    roots = [path for path, props in nodes.items() if any(c in ('mediatek,mtu3', 'mediatek,xsphy', 'mediatek,extcon-usb', 'mediatek,mt6375-tcpc', 'mediatek,mt6589-wdt') for c in strings(props.get('compatible', b'')))]
    found, edges, visited = {}, [], set()

    def visit(path):
        if path in visited:
            return
        visited.add(path)
        props = nodes[path]
        compat = strings(props.get('compatible', b''))
        matches = sorted({name for c in compat for name in aliases.get(c, set())})
        found[path] = {'compatible': compat, 'status': strings(props.get('status', b'okay\0')),
                       'matching_stock_modules': matches, 'modules_absent_from_native_load_list': [n for n in matches if n not in selected]}
        parent = path.rsplit('/', 1)[0] or '/'
        if path != '/' and parent in nodes:
            edges.append({'consumer': path, 'property': 'parent', 'supplier': parent})
            visit(parent)
        for name, value in props.items():
            if name in ('clocks', 'phys', 'power-domains', 'io-channels', 'resets'):
                cell_key = {'clocks': '#clock-cells', 'phys': '#phy-cells', 'power-domains': '#power-domain-cells', 'io-channels': '#io-channel-cells', 'resets': '#reset-cells'}[name]
                words, index = cells(value), 0
                while index < len(words):
                    supplier = phandles.get(words[index])
                    if supplier is None:
                        break
                    edges.append({'consumer': path, 'property': name, 'supplier': supplier})
                    visit(supplier)
                    if cell_key not in nodes[supplier]:
                        break
                    index += 1 + cells(nodes[supplier][cell_key])[0]
            elif name.endswith('-supply') or name in ('charger', 'remote-endpoint'):
                if len(value) == 4 and cells(value)[0] in phandles:
                    supplier = phandles[cells(value)[0]]
                    edges.append({'consumer': path, 'property': name, 'supplier': supplier})
                    visit(supplier)

    for path in roots:
        visit(path)
    boot = read_boot_v4((CANDIDATE / 'nord3-busybox-candidate.img').read_bytes())
    watchdog = module_root / 'mtk_wdt.ko'
    report = {'candidate_sha256': hashlib.sha256((CANDIDATE / 'nord3-busybox-candidate.img').read_bytes()).hexdigest(),
              'boot_cmdline': boot['cmdline'], 'dtb_sha256': hashlib.sha256(raw).hexdigest(),
              'fdt': info, 'roots': roots, 'nodes': found, 'supplier_edges': edges,
              'watchdog_module_sha256': hashlib.sha256(watchdog.read_bytes()).hexdigest(),
              'watchdog_in_stock_load_order': 'mtk_wdt.ko' in (module_root / 'modules.load').read_text().splitlines(),
              'watchdog_in_native_load_order': 'mtk_wdt.ko' in selected,
              'phone_contacted': False, 'hardware_failure_cause_confirmed': False,
              'limits': ['Audits stock base FDT, not actual installed DTB or selected/applied DTBO.',
                         'OF aliases are candidates, not proof of successful driver binding.',
                         'Module symbol dependencies do not express all device-tree supplier dependencies.',
                         'Disabled nodes and alternative USB controllers may be included; actual boot selection is unknown.']}
    (BASE / 'docs/early-boot-supplier-audit.json').write_text(json.dumps(report, indent=2) + '\n')
    print('Stock watchdog omitted:', not report['watchdog_in_native_load_order'])
    print('Candidate cmdline:', boot['cmdline'])
    for path, item in found.items():
        if item['modules_absent_from_native_load_list']:
            print(path, item['status'], 'omitted module candidates:', ', '.join(item['modules_absent_from_native_load_list']))


if __name__ == '__main__':
    main()
