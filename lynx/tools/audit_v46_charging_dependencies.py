"""Compare matching stock charging module dependencies with a V46 inventory."""

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'linux-port'))
from image_formats import module_metadata  # noqa: E402

STOCK = ROOT / 'linux-port/artifacts/stock-cph2493-August-eu-ota'
SOURCES = (STOCK / 'vendor-ramdisk-unpacked/lib/modules',
           STOCK / 'wifi-reference/vendor-dlkm-unpacked/lib/modules')
TARGETS = ('tcpc_mt6375.ko', 'oplus_chg.ko', 'mt6375-battery.ko')


def normalize(name):
    return name.removesuffix('.ko').replace('-', '_')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inventory', required=True, type=Path)
    args = parser.parse_args()
    inventory = args.inventory.resolve(strict=True)
    if not inventory.is_relative_to(ROOT / 'logs'):
        raise ValueError('Inventory must be under Lynx logs')
    capture = json.loads(inventory.read_text())
    if capture.get('state') != 'v46-charging-readonly-captured':
        raise ValueError('Incomplete live charging inventory')
    loaded = set(capture['loaded_modules'])
    index = {}
    for source in SOURCES:
        for path in source.glob('*.ko'):
            index.setdefault(normalize(path.name), path)
    metadata = {}

    def module(name):
        canonical = normalize(name)
        if canonical not in metadata:
            path = index[canonical]
            raw = path.read_bytes()
            fields = module_metadata(raw)['values']
            dependencies = [x for group in fields.get('depends', [])
                            for x in group.split(',') if x]
            metadata[canonical] = {
                'path': str(path.relative_to(ROOT)),
                'sha256': hashlib.sha256(raw).hexdigest(),
                'vermagic': fields.get('vermagic'),
                'depends': [normalize(x) for x in dependencies],
            }
        return metadata[canonical]

    targets = {}
    for target in TARGETS:
        visiting, order = set(), []

        def visit(name):
            canonical = normalize(name)
            if canonical in order:
                return
            if canonical in visiting:
                raise ValueError('Cyclic module dependency')
            visiting.add(canonical)
            for dependency in module(canonical)['depends']:
                visit(dependency)
            visiting.remove(canonical)
            order.append(canonical)

        visit(target)
        targets[target] = {
            'load_order_if_ever_reviewed': order,
            'absent_now': [name for name in order if name not in loaded],
            'module': module(target),
        }
    report = {
        'state': 'v46-charging-offline-dependencies-audited',
        'inventory': str(inventory),
        'boot_id': capture['boot_id'],
        'sources': [str(p.relative_to(ROOT)) for p in SOURCES],
        'modules': metadata,
        'targets': targets,
        'phone_contacted': False,
        'module_loads': False,
        'partition_writes': False,
        'limits': 'Dependency closure and matching vermagic do not establish safe probe behavior, DT readiness, or charging/thermal policy.',
    }
    out = ROOT / 'logs' / f'v46-charging-dependencies-{time.time_ns()}.json'
    out.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'state': report['state'], 'result': str(out),
                      'absent': {name: info['absent_now']
                                 for name, info in targets.items()}}))


if __name__ == '__main__':
    main()
