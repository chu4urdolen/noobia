"""Read-only stock DT/module audit for the UFS hardware reset supplier."""
import hashlib
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
P = ROOT / 'linux-port'
sys.path.insert(0, str(P))
from image_formats import elf64, module_metadata, require

S = P / 'artifacts/stock-cph2493-August-eu-ota'


def fdt_nodes(data):
    prefix = data.find(bytes.fromhex('d00dfeed'))
    require(prefix >= 0, 'Missing FDT')
    data = data[prefix:]
    _, total, structure, strings, _, version, _, _, strings_size, structure_size = struct.unpack_from('>10I', data)
    require(version == 17 and total <= len(data), 'Unexpected FDT bounds/version')
    require(structure + structure_size <= total and strings + strings_size <= total, 'FDT section bounds')
    nodes, stack = {}, []
    position = structure
    while position < structure + structure_size:
        token = struct.unpack_from('>I', data, position)[0]
        position += 4
        if token == 1:
            end = data.index(b'\0', position)
            stack.append(data[position:end].decode())
            nodes['/' + '/'.join(stack[1:])] = {}
            position = (end + 4) & ~3
        elif token == 2:
            stack.pop()
        elif token == 3:
            size, name_offset = struct.unpack_from('>2I', data, position)
            position += 8
            require(name_offset < strings_size and position + size <= structure + structure_size, 'FDT property bounds')
            end = data.index(b'\0', strings + name_offset)
            name = data[strings + name_offset:end].decode()
            nodes['/' + '/'.join(stack[1:])][name] = data[position:position + size]
            position = (position + size + 3) & ~3
        elif token == 9:
            break
        else:
            require(token == 4, 'Unexpected FDT token')
    return nodes


def versions(data):
    return {name.split(b'\0', 1)[0].decode(): crc
            for crc, name in struct.iter_unpack('<Q56s', elf64(data)['sections']['__versions'])}


def main():
    dtb = S / 'unpacked-vendor-boot/dtb'
    nodes = fdt_nodes(dtb.read_bytes())
    reset_nodes = {path: properties for path, properties in nodes.items()
                   if b'ti,syscon-reset' in properties.get('compatible', b'').split(b'\0')}
    require(reset_nodes, 'No matching reset supplier in stock DT')
    require(any(props.get('status', b'okay\0').rstrip(b'\0') in [b'okay', b'ok'] for props in reset_nodes.values()), 'Reset supplier disabled')
    audit = json.loads((P / 'docs/wifi-boot-module-audit.json').read_text())
    reset_path = S / 'vendor-ramdisk-unpacked/lib/modules/reset-ti-syscon.ko'
    reset = reset_path.read_bytes()
    metadata = module_metadata(reset)['values']
    require(metadata['depends'] == [''], 'Additional reset module dependencies need audit')
    imported = versions(reset)
    conflicts = []
    for entry in audit['modules']:
        raw = Path(entry['file']).read_bytes()
        require(hashlib.sha256(raw).hexdigest() == entry['sha256'], 'Previous audited module changed')
        require(metadata['vermagic'] == module_metadata(raw)['values']['vermagic'], 'Reset vermagic mismatch')
        previous = versions(raw)
        require(imported['module_layout'] == previous['module_layout'], 'Reset layout mismatch')
        for symbol in imported.keys() & previous.keys():
            if imported[symbol] != previous[symbol]:
                conflicts.append({'symbol': symbol, 'module': entry['name']})
    require(not conflicts, 'Reset import CRC conflict')
    ufs = (S / 'vendor-ramdisk-unpacked/lib/modules/ufs-mediatek-mod.ko').read_bytes()
    require(b'ti,syscon-reset\0' in ufs, 'Stock UFS supplier literal absent')
    source = (P / 'docs/wifi-source-reference/ufs-mediatek.c').read_bytes()
    require(b'DL_STATE_DORMANT' in source and b'DL_FLAG_AUTOPROBE_CONSUMER' in source, 'Published supplier guard absent')
    report = {'passed': True, 'phone_contacted': False, 'reset_module': str(reset_path),
              'reset_module_sha256': hashlib.sha256(reset).hexdigest(), 'vermagic': metadata['vermagic'],
              'module_layout_crc': hex(imported['module_layout']), 'imported_symbol_crc_conflicts': conflicts,
              'stock_dtb_sha256': hashlib.sha256(dtb.read_bytes()).hexdigest(),
              'reset_nodes': {path: {'compatible': props['compatible'].rstrip(b'\0').decode().split('\0'),
                                    'status': props.get('status', b'okay\0').rstrip(b'\0').decode(),
                                    'phandle': props.get('phandle', b'').hex()}
                              for path, props in reset_nodes.items()},
              'ufs_nodes': [path for path in nodes if 'ufshci' in path],
              'published_source_sha256': hashlib.sha256(source).hexdigest(),
              'limits': 'Stock base DT and module ABI, not a captured runtime merged DT or a successful physical UFS probe.'}
    target = P / 'docs/ufs-reset-supplier-audit.json'
    target.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
