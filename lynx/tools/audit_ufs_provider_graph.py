"""Resolve stock UFS DT phandles and match provider compatibles to stock modules."""
import argparse
import fnmatch
import hashlib
import json
import struct
import re
from pathlib import Path
from audit_ufs_reset_supplier import fdt_nodes
from image_formats import module_metadata

ROOT = Path(__file__).resolve().parent.parent
P = ROOT / 'linux-port'
S = P / 'artifacts/stock-cph2493-August-eu-ota'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dtb', type=Path, default=S / 'unpacked-vendor-boot/dtb')
    parser.add_argument('--output', type=Path, default=P / 'docs/ufs-provider-graph.json')
    args = parser.parse_args()
    nodes = fdt_nodes(args.dtb.read_bytes())
    handles = {int.from_bytes(properties['phandle'], 'big'): path
               for path, properties in nodes.items() if 'phandle' in properties}
    aliases, literals = {}, {}
    for file in (S / 'vendor-ramdisk-unpacked/lib/modules').glob('*.ko'):
        raw = file.read_bytes()
        aliases[file.name] = module_metadata(raw)['values'].get('alias', [])
        literals[file.name] = {value[:-1].decode() for value in re.findall(rb'(?:mediatek|ti),[a-zA-Z0-9_.-]+\x00', raw)}
    manifest = json.loads((P / 'artifacts/busybox-wifi-ssh-twostage-v4/build-validation.json').read_text())
    loaded = set(manifest['base_modules'] + manifest['storage_modules'])
    target = '/ufshci@112b0000'
    queue, visited, edges = [target], set(), []
    while queue:
        path = queue.pop(0)
        if path in visited:
            continue
        visited.add(path)
        props = nodes[path]
        for key, data in props.items():
            if key not in ['clocks', 'phys', 'resets', 'power-domains', 'pinctrl-0', 'mediatek,syscon'] and not key.endswith('-supply'):
                continue
            if len(data) % 4:
                continue
            cells = list(struct.unpack('>' + str(len(data) // 4) + 'I', data))
            index = 0
            while index < len(cells):
                provider = handles.get(cells[index])
                if provider is None:
                    break
                pp = nodes[provider]
                count_key = {'clocks': '#clock-cells', 'phys': '#phy-cells', 'resets': '#reset-cells', 'power-domains': '#power-domain-cells'}.get(key)
                count = int.from_bytes(pp.get(count_key, b''), 'big') if count_key else 0
                compatible_paths = []
                ancestor = provider
                for _ in range(3):
                    if nodes.get(ancestor, {}).get('compatible'):
                        compatible_paths.append(ancestor)
                    if ancestor == '/':
                        break
                    ancestor = ancestor.rsplit('/', 1)[0] or '/'
                candidates = []
                for candidate in compatible_paths:
                    compatibles = nodes[candidate]['compatible'].rstrip(b'\0').decode().split('\0')
                    matches = [name for name, patterns in aliases.items()
                               if any(fnmatch.fnmatchcase('of:NproviderT*C' + c, alias)
                                      or fnmatch.fnmatchcase('of:NproviderT*C' + c + 'C', alias)
                                      for c in compatibles for alias in patterns if alias.startswith('of:'))]
                    candidates.append({'node': candidate, 'compatible': compatibles, 'matching_modules': matches,
                                       'compatible_literal_modules': [name for name, strings in literals.items() if set(compatibles) & strings],
                                       'not_loaded_before_ufs': sorted(set(matches) - loaded)})
                    if candidate not in visited:
                        queue.append(candidate)
                edges.append({'consumer': path, 'property': key, 'provider': provider,
                              'specifier': cells[index + 1:index + 1 + count], 'driver_candidates': candidates})
                queue.append(provider)
                index += 1 + count
    output = args.output
    report = {'phone_contacted': False, 'dtb': str(args.dtb), 'dtb_sha256': hashlib.sha256(args.dtb.read_bytes()).hexdigest(), 'target': target, 'edges': edges,
              'limits': 'Base stock DT and OF alias candidates only. Parents are included for MFD/regulator children; module matches do not prove a required active binding. Runtime DT overlays and driver-specific implicit dependencies may differ.'}
    output.write_text(json.dumps(report, indent=2) + '\n')
    for edge in edges:
        if edge['consumer'] == target:
            print(json.dumps(edge))
    print('Saved:', output)


if __name__ == '__main__':
    main()
