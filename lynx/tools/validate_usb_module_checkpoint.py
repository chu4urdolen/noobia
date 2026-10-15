"""Independent fixed-image checks for the with-MTU3 diagnostic; no phone access."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
PROJECT = ROOT / 'linux-port'
sys.path.insert(0, str(PROJECT))
from image_formats import read_boot_v4, read_newc, module_metadata, require
from ramdisk_codec import decompress


def main():
    folder = PROJECT / 'artifacts/busybox-usb-module-checkpoints/with-mtu3'
    expected = '5bb984899b19c9e739faa23aa9039374a5ad20ab99c10948d5d2b964da3616d6'
    image = (folder / 'nord3-busybox-candidate.img').read_bytes()
    require(hashlib.sha256(image).hexdigest() == expected, 'Diagnostic image changed')
    stock = PROJECT / 'artifacts/stock-cph2493-August-eu-ota'
    boot = read_boot_v4(image)
    require(boot['kernel'] == read_boot_v4((stock / 'boot.img').read_bytes())['kernel'], 'Stock kernel mismatch')
    generic = read_newc(decompress(boot['ramdisk']))
    vendor = read_newc(decompress((stock / 'unpacked-vendor-boot/vendor_ramdisk00').read_bytes()))
    combined = {**vendor, **generic}
    init = generic['init']['data']
    require(init == (folder / 'init-source').read_bytes(), 'Frozen init changed')
    proof = (PROJECT / 'init-boot-proof').read_bytes()
    guard = proof[proof.index(b'wdt_ready=0'):proof.index(b'\nif [ "$wdt_ready"')]
    require(init.count(guard) == 2, 'Exact reset guard must precede and follow module loads')
    require((PROJECT / 'usb-module-checkpoint.sh').read_bytes() in init, 'Module helper changed')
    require(init.count(b'/bin/boot-proof-reboot\n') == 1, 'Expected one supported reset request')
    require(b'lynx_load_checkpoint_modules /etc/lynx-checkpoint-modules.load || stop' in init, 'Module failure must stop')
    require(b'configfs' not in init and b'usb_mode' not in init and b'mdev' not in init, 'Unexpected USB setup')
    require(generic['bin/boot-proof-reboot']['data'] == read_newc(decompress(read_boot_v4((PROJECT / 'artifacts/busybox-August-boot-proof-bound-guards/nord3-busybox-candidate.img').read_bytes())['ramdisk']))['bin/boot-proof-reboot']['data'], 'Proven helper mismatch')
    names = generic['etc/lynx-checkpoint-modules.load']['data'].decode().splitlines()
    known = (PROJECT / 'artifacts/busybox-August-usb-device-xhci/usb-modules.load').read_text().splitlines()
    require(names == [name for name in known if name != 'mtk_wdt.ko'], 'Unexpected module sequence')
    require(len(set(names)) == len(names) == 34, 'Unexpected module count')
    audit = json.loads((PROJECT / 'docs/august-vendor-ramdisk-audit.json').read_text())
    hashes = {item['path']: item['sha256'] for item in audit['entries']}
    for name in ['mtk_wdt.ko', 'reboot-mode.ko', 'syscon-reboot-mode.ko', *names]:
        path = 'lib/modules/' + name
        data = combined[path]['data']
        require(hashlib.sha256(data).hexdigest() == hashes[path], 'Stock module changed: ' + name)
        require(module_metadata(data)['values']['scmversion'] == ['g311738fbb5a8'], 'Module version mismatch')
    vm_path = PROJECT / 'artifacts/emulated-module-checkpoint-with-mtu3-1791667912949232589/result.json'
    vm = json.loads(vm_path.read_text())
    require(vm['candidate_sha256'] == expected and vm['module_checkpoint_failure_guard_observed'] and not vm['kernel_reboot_command_observed'], 'VM guard validation mismatch')
    tests_path = ROOT / 'tools/test-artifacts/busybox-usb-checkpoints-1791667910990513433/result.json'
    tests = json.loads(tests_path.read_text())
    require(tests['passed'] and len(tests['cases']) == 6, 'Shell fixture failure')
    for path, digest in tests['sources'].items():
        require(hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest, 'Tested shell source changed')
    model = ROOT / 'tools/avb-host/avb-boot-model'
    ref = json.loads((PROJECT / 'docs/avb-boot-model-results.json').read_text())
    require(hashlib.sha256(model.read_bytes()).hexdigest() == ref['binary_sha256'], 'AVB model changed')
    cases = []
    for unlocked in ['1', '0']:
        process = subprocess.run([str(model), str(stock), str(folder / 'nord3-busybox-candidate.img'), '0', unlocked], capture_output=True, text=True, timeout=20)
        require(process.returncode == 0, 'AVB model failure')
        cases.append(json.loads(process.stdout))
    require(cases[0]['slot_data_returned'] and cases[0]['boot_partitions_loaded'] == 1 and not cases[1]['slot_data_returned'], 'Modeled AVB policy mismatch')
    report = dict(passed=True, phone_contacted=False, candidate_sha256=expected, stock_module_count=37, vm_receipt=str(vm_path), shell_test_receipt=str(tests_path), avb_policy_cases=cases, limits='Host policy model and VM guard checks do not prove hardware driver loading or USB.')
    output = PROJECT / 'docs/usb-module-checkpoint-validation.json'
    output.write_text(json.dumps(report, indent=2) + '\n')
    print('Independent checkpoint validation passed:', output)


if __name__ == '__main__':
    main()
