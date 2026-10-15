"""Validate fixed dependency-complete module prefixes offline."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
PROJECT = ROOT / 'linux-port'
sys.path.insert(0, str(PROJECT))
from image_formats import read_boot_v4, read_newc, require, module_metadata
from ramdisk_codec import decompress

HASHES = {'5': '7212931718e7814f411ade49500da0f72ce074b0a8be1ea56eebab24435f3bad',
          '17': '5a082af55c3388ad9aa70f3d2a3b39d26d5ce1bc7e79d4bd0de5c55a879b7b79',
          '26': 'd55a995c513572af8dc5f72476962ca086e0b301a6ea143e81d78f032be1e344',
          '33': '0208f76c1ef5d7e523dbf83226c208f0a0d8f2c08768cbbdfb79025275fd9ece'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--prefix', choices=HASHES, default='17')
    args = parser.parse_args()
    folder = PROJECT / 'artifacts/busybox-usb-module-prefixes' / args.prefix
    if args.prefix == '33':
        folder = PROJECT / 'artifacts/busybox-usb-module-checkpoints/suppliers'
    image = (folder / 'nord3-busybox-candidate.img').read_bytes()
    require(hashlib.sha256(image).hexdigest() == HASHES[args.prefix], 'Prefix image changed')
    base = (PROJECT / 'artifacts/busybox-usb-module-checkpoints/with-mtu3/nord3-busybox-candidate.img').read_bytes()
    require(hashlib.sha256(base).hexdigest() == '5bb984899b19c9e739faa23aa9039374a5ad20ab99c10948d5d2b964da3616d6', 'Checkpoint reference changed')
    boot, fullboot = read_boot_v4(image), read_boot_v4(base)
    require(len(image) == len(base) == 67108864 and boot['kernel'] == fullboot['kernel'], 'Kernel or geometry differs')
    entries, original = read_newc(decompress(boot['ramdisk'])), read_newc(decompress(fullboot['ramdisk']))
    require(entries.keys() == original.keys(), 'Archive membership changed')
    require([name for name in original if original[name] != entries[name]] == ['etc/lynx-checkpoint-modules.load'], 'Unexpected archive modification')
    names = entries['etc/lynx-checkpoint-modules.load']['data'].decode().splitlines()
    fullnames = original['etc/lynx-checkpoint-modules.load']['data'].decode().splitlines()
    require(names == fullnames[:int(args.prefix)] and len(names) == len(set(names)), 'Wrong prefix')
    coverage = struct.unpack('!4sIIQQQ28x', base[-64:])[3]
    require(image[coverage:] == base[coverage:], 'OEM metadata tail changed')
    stock = PROJECT / 'artifacts/stock-cph2493-August-eu-ota'
    vendor = read_newc(decompress((stock / 'unpacked-vendor-boot/vendor_ramdisk00').read_bytes()))
    combined = {**vendor, **entries}
    audit = json.loads((PROJECT / 'docs/august-vendor-ramdisk-audit.json').read_text())
    expected = {item['path']: item['sha256'] for item in audit['entries']}
    deps = {}
    for line in (stock / 'vendor-ramdisk-unpacked/lib/modules/modules.dep').read_text().splitlines():
        name, _, values = line.partition(':')
        deps[Path(name).name] = [Path(value).name for value in values.split()]
    loaded = set()
    for name in ['mtk_wdt.ko', 'reboot-mode.ko', 'syscon-reboot-mode.ko', *names]:
        require(set(deps[name]) <= loaded, 'Dependency order failure: ' + name)
        path = 'lib/modules/' + name
        data = combined[path]['data']
        require(hashlib.sha256(data).hexdigest() == expected[path], 'Stock module changed')
        require(module_metadata(data)['values']['scmversion'] == ['g311738fbb5a8'], 'Module version mismatch')
        loaded.add(name)
    checked = json.loads((PROJECT / 'docs/usb-module-checkpoint-validation.json').read_text())
    require(checked['passed'] and checked['candidate_sha256'] == hashlib.sha256(base).hexdigest(), 'Full init validation missing')
    vms = sorted((PROJECT / 'artifacts').glob('emulated-module-prefix-17-*/result.json'))
    require(bool(vms), 'Halfway VM guard evidence absent')
    vm = json.loads(vms[-1].read_text())
    require(vm['candidate_sha256'] == HASHES['17'] and vm['module_checkpoint_failure_guard_observed'] and not vm['kernel_reboot_command_observed'], 'Halfway VM guard mismatch')
    model = ROOT / 'tools/avb-host/avb-boot-model'
    model_ref = json.loads((PROJECT / 'docs/avb-boot-model-results.json').read_text())
    require(hashlib.sha256(model.read_bytes()).hexdigest() == model_ref['binary_sha256'], 'AVB model changed')
    cases = []
    for unlocked in ['1', '0']:
        process = subprocess.run([str(model), str(stock), str(folder / 'nord3-busybox-candidate.img'), '0', unlocked], capture_output=True, text=True, timeout=20)
        require(process.returncode == 0, 'AVB model failed')
        cases.append(json.loads(process.stdout))
    require(cases[0]['slot_data_returned'] and cases[0]['boot_partitions_loaded'] == 1 and not cases[1]['slot_data_returned'], 'AVB policy differs')
    result = dict(passed=True, prefix=int(args.prefix), candidate_sha256=HASHES[args.prefix], stock_module_count=len(loaded), dependency_order_checked=True, exact_init_unchanged=True, vm_receipt=str(vms[-1]), avb_cases=cases, phone_contacted=False, hardware_loading_proven=False, limits='The VM checks identical init refusal without real reset devices; only prefix17 was emulated. Module insertion does not prove hardware binding.')
    output = PROJECT / 'docs' / ('usb-module-prefix-' + args.prefix + '-validation.json')
    output.write_text(json.dumps(result, indent=2) + '\n')
    print('Prefix validation passed:', output)


if __name__ == '__main__':
    main()
