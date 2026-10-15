"""Independent guarded-module/image checks and recorded stock-kernel execution."""
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
PROJECT = ROOT / 'linux-port'
sys.path.insert(0, str(PROJECT))
from image_formats import read_boot_v4, read_newc, module_metadata, require
from ramdisk_codec import decompress


def main():
    stock = PROJECT / 'artifacts/stock-cph2493-August-eu-ota'
    old_module = (stock / 'vendor-ramdisk-unpacked/lib/modules/mtu3.ko').read_bytes()
    new_module = (PROJECT / 'artifacts/mtu3-null-child-guard/mtu3.ko').read_bytes()
    require(hashlib.sha256(old_module).hexdigest() == 'd3c59fa794a6e02f014dd0de660592bb66c9d7f8eb941c1d1183f8a3322bb467', 'Original module changed')
    require(hashlib.sha256(new_module).hexdigest() == '49688170d2be04c5051331f93ddf8eda8d8bc5ce37baf82dd04d2edb7f657223', 'Guarded module changed')
    start = 25808
    require(old_module[start:start+12] == struct.pack('<III', 0xaa0003e8, 0xf9404d08, 0x2a1f03e0), 'Original instruction mismatch')
    require(new_module[start:start+12] == struct.pack('<III', 0xf9404c08, 0x2a1f03e0, 0xb4000068), 'Guard instruction mismatch')
    require(old_module[:start] == new_module[:start] and old_module[start+12:] == new_module[start+12:], 'Unrelated module changes')
    require(module_metadata(old_module) == module_metadata(new_module), 'Module metadata changed')
    folder = PROJECT / 'artifacts/busybox-mtu3-null-guard-checkpoint'
    image = (folder / 'nord3-busybox-candidate.img').read_bytes()
    digest = hashlib.sha256(image).hexdigest()
    require(digest == 'c815d527d6a4ff54f4ef2e04f968a7e4a6cf0a51e6e2eb1bba33df3e411c7c6c', 'Guard image changed')
    original = (PROJECT / 'artifacts/busybox-usb-module-checkpoints/with-mtu3/nord3-busybox-candidate.img').read_bytes()
    require(hashlib.sha256(original).hexdigest() == '5bb984899b19c9e739faa23aa9039374a5ad20ab99c10948d5d2b964da3616d6', 'Full checkpoint changed')
    boot, oldboot = read_boot_v4(image), read_boot_v4(original)
    require(len(image) == len(original) == 67108864 and boot['kernel'] == oldboot['kernel'], 'Kernel/geometry changed')
    entries, before = read_newc(decompress(boot['ramdisk'])), read_newc(decompress(oldboot['ramdisk']))
    require(entries.keys() == before.keys() and [name for name in before if before[name] != entries[name]] == ['lib/modules/mtu3.ko'], 'Unexpected archive change')
    require(entries['lib/modules/mtu3.ko']['data'] == new_module, 'Wrong module overlay')
    vendor = read_newc(decompress((stock / 'unpacked-vendor-boot/vendor_ramdisk00').read_bytes()))
    require({**vendor, **entries}['lib/modules/mtu3.ko']['data'] == new_module, 'Vendor-before-generic overlay mismatch')
    coverage = struct.unpack('!4sIIQQQ28x', original[-64:])[3]
    require(image[coverage:] == original[coverage:], 'Metadata tail changed')
    vm_path = PROJECT / 'artifacts/emulated-mtu3-null-guard-1791670663767994158/result.json'
    vm = json.loads(vm_path.read_text())
    require(vm['passed'] and vm['stock_and_guarded_module_load_passed'] and vm['modified_module_sha256'] == hashlib.sha256(new_module).hexdigest(), 'ARM64/module-load test failed')
    require(len(vm['cases']) == 6 and vm['exit_code'] == 0 and not vm['timed_out'], 'Incomplete execution test')
    model = ROOT / 'tools/avb-host/avb-boot-model'
    ref = json.loads((PROJECT / 'docs/avb-boot-model-results.json').read_text())
    require(hashlib.sha256(model.read_bytes()).hexdigest() == ref['binary_sha256'], 'AVB model changed')
    cases = []
    for unlocked in ['1', '0']:
        process = subprocess.run([str(model), str(stock), str(folder / 'nord3-busybox-candidate.img'), '0', unlocked], capture_output=True, text=True, timeout=20)
        require(process.returncode == 0, 'AVB model failed')
        cases.append(json.loads(process.stdout))
    require(cases[0]['slot_data_returned'] and cases[0]['boot_partitions_loaded'] == 1 and not cases[1]['slot_data_returned'], 'Guard image policy mismatch')
    result = dict(passed=True, phone_contacted=False, candidate_sha256=digest, only_changed_archive_entry='lib/modules/mtu3.ko', instruction_change_region_bytes=12, all_other_module_bytes_identical=True, stock_kernel_module_load_passed=True, vm_receipt=str(vm_path), avb_cases=cases, hardware_fix_proven=False, limits='Stock-kernel VM loading and instruction tests passed; MT6983 probe/binding and concurrency remain untested. The guard does not prove the cause of the prior failure.')
    output = PROJECT / 'docs/mtu3-guard-checkpoint-validation.json'
    output.write_text(json.dumps(result, indent=2) + '\n')
    print('Guard checkpoint independent checks passed:', output)


if __name__ == '__main__':
    main()
