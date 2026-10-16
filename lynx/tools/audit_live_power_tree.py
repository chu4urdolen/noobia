"""Offline power-node and stock-module audit from a verified live FDT capture."""
import argparse
import hashlib
import json
import struct
from pathlib import Path

from audit_ufs_reset_supplier import fdt_nodes, module_metadata, versions

ROOT = Path(__file__).resolve().parent.parent
STOCK = ROOT / 'linux-port/artifacts/stock-cph2493-August-eu-ota'
KERNEL = '5.10.149-android12-9-o-g311738fbb5a8'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--receipt', type=Path, required=True)
    args = parser.parse_args()
    receipt = json.loads(args.receipt.read_text())
    operation = next(op for op in receipt['operations'] if op['name'] == 'command')
    raw = args.receipt.with_name('command.stdout').read_bytes()
    if not receipt.get('native_identity_verified') or operation['exit_code'] != 0:
        raise ValueError('Verified native capture required')
    if hashlib.sha256(raw).hexdigest() != operation['stdout_sha256']:
        raise ValueError('Capture hash mismatch')
    if raw[:4] != bytes.fromhex('d00dfeed'):
        raise ValueError('Expected raw live FDT capture')
    nodes = fdt_nodes(raw)
    selected = {}
    text_properties = {'compatible', 'status', 'suspend-method'}
    cell_properties = {'reg', 'lpm-kernel-suspend', 'arm,psci-suspend-param', 'entry-latency-us',
                       'exit-latency-us', 'min-residency-us'}
    for path, properties in nodes.items():
        compatible = properties.get('compatible', b'')
        if not any(term in (path.encode() + b'\0' + compatible).lower() for term in
                   [b'mtk-lpm', b'mtk_lpm', b'cpupm', b'mcusys-ctrl', b'mcupm', b'sspm', b'scmi', b'idle-state']):
            continue
        fields = {}
        for name in text_properties & properties.keys():
            fields[name] = properties[name].rstrip(b'\0').decode().split('\0')
        for name in cell_properties & properties.keys():
            value = properties[name]
            fields[name] = [hex(cell[0]) for cell in struct.iter_unpack('>I', value)] if len(value) % 4 == 0 else {'hex': value.hex()}
        selected[path] = fields
    folders = [STOCK / 'wifi-reference/vendor-dlkm-unpacked/lib/modules',
               STOCK / 'vendor-ramdisk-unpacked/lib/modules']
    index = {}
    for folder in folders:
        for path in folder.glob('*.ko'):
            index.setdefault(path.stem.replace('-', '_'), []).append(path)
    roots = ['mtk_lpm', 'mtk_lpm_dbg_common_v1', 'mtk_lpm_plat_v1', 'mtk_lpm_dbg_mt6983', 'mcupm', 'sspm_v3']
    modules, pending, shared_crcs, conflicts = {}, list(roots), {}, []
    while pending:
        name = pending.pop()
        if name in modules:
            continue
        candidates = index.get(name)
        if not candidates:
            raise ValueError('Missing stock module dependency: ' + name)
        blobs = [path.read_bytes() for path in candidates]
        digests = {hashlib.sha256(blob).hexdigest() for blob in blobs}
        if len(digests) != 1:
            raise ValueError('Ambiguous stock module copies: ' + name)
        blob = blobs[0]
        metadata = module_metadata(blob)['values']
        if not metadata['vermagic'][0].startswith(KERNEL + ' '):
            raise ValueError('Unexpected module kernel: ' + name)
        dependencies = [dep.replace('-', '_') for dep in metadata.get('depends', [''])[0].split(',') if dep]
        imports = versions(blob)
        for symbol, crc in imports.items():
            if symbol in shared_crcs and shared_crcs[symbol] != crc:
                conflicts.append({'module': name, 'symbol': symbol})
            shared_crcs[symbol] = crc
        modules[name] = {'path': str(candidates[0]), 'sha256': next(iter(digests)),
                         'depends': dependencies, 'vermagic': metadata['vermagic'][0],
                         'import_count': len(imports), 'module_layout_crc': hex(imports['module_layout'])}
        pending.extend(dependencies)
    if conflicts:
        raise ValueError('Shared import CRC conflicts: ' + repr(conflicts))
    result = {'live_fdt_sha256': hashlib.sha256(raw).hexdigest(), 'live_fdt_bytes': len(raw),
              'node_count': len(nodes), 'selected_nodes': selected, 'module_roots': roots,
              'module_dependency_closure': modules, 'shared_import_crc_conflicts': conflicts,
              'phone_contacted_by_audit': False, 'modules_loaded': False,
              'limits': ['Matching metadata/shared import CRCs do not prove safe initialization.',
                         'DT nodes and absent status are not proof that their driver is bound.',
                         'Firmware readiness and PSCI rejection cause remain unverified.']}
    output = args.receipt.with_name('power-tree-analysis.json')
    output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'analysis': str(output), 'selected_nodes': len(selected),
                      'module_dependency_closure': sorted(modules), 'crc_conflicts': len(conflicts)}))


if __name__ == '__main__':
    main()
