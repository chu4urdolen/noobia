"""Independently compare the fixed hold control with the minimal reference."""
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
PROJECT = ROOT / 'linux-port'
sys.path.insert(0, str(PROJECT))
from image_formats import read_boot_v4, read_newc, require
from ramdisk_codec import decompress


def main():
    checked = subprocess.run(['python3', str(ROOT / 'tools/validate_boot_proof.py')], capture_output=True, text=True, timeout=30)
    require(checked.returncode == 0, 'Reference validation failed: ' + checked.stdout + checked.stderr)
    folder = PROJECT / 'artifacts/busybox-minimal-hold-control'
    image = (folder / 'nord3-busybox-candidate.img').read_bytes()
    digest = hashlib.sha256(image).hexdigest()
    require(digest == '25040803f00546bda46ba58407f19e7dcf1978375466a210df360cbcdd2f9166', 'Control changed')
    reference = (PROJECT / 'artifacts/busybox-August-boot-proof-bound-guards/nord3-busybox-candidate.img').read_bytes()
    boot, refboot = read_boot_v4(image), read_boot_v4(reference)
    require(len(image) == len(reference) == 67108864 and boot['kernel'] == refboot['kernel'], 'Kernel or image geometry changed')
    entries = read_newc(decompress(boot['ramdisk']))
    original = read_newc(decompress(refboot['ramdisk']))
    require(entries.keys() == original.keys(), 'Archive membership changed')
    require([name for name in original if original[name] != entries[name]] == ['init'], 'Control changes more than init')
    before = b"    log 'BOUND_STOCK_DRIVERS; REQUESTING_ONE_RESTART2_BOOTLOADER'\n    /bin/boot-proof-reboot\n    log 'REBOOT_SYSCALL_RETURNED; NO_RETRY'"
    after = b"    log 'BOUND_STOCK_DRIVERS; HOLD_CONTROL_NO_REBOOT_REQUEST'"
    require(original['init']['data'].count(before) == 1, 'Reference block changed')
    require(entries['init']['data'] == original['init']['data'].replace(before, after) == (folder / 'init-source').read_bytes(), 'Unexpected init change')
    for key in ['mode', 'uid', 'gid', 'rdevmajor', 'rdevminor']:
        require(entries['init'][key] == original['init'][key], 'Init metadata changed')
    coverage = struct.unpack('!4sIIQQQ28x', reference[-64:])[3]
    require(image[coverage:] == reference[coverage:], 'OEM metadata tail changed')
    fixture = ROOT / 'tools/test-artifacts/boot-hold-control-1791668614253554039/result.json'
    tests = json.loads(fixture.read_text())
    require(tests['passed'] and len(tests['cases']) == 4, 'Branch fixtures failed')
    for path, expected in tests['source_sha256'].items():
        require(hashlib.sha256(Path(path).read_bytes()).hexdigest() == expected, 'Tested source changed')
    vm_paths = sorted((PROJECT / 'artifacts').glob('emulated-minimal-hold-control-*/result.json'))
    require(bool(vm_paths), 'Control VM evidence missing')
    vm = json.loads(vm_paths[-1].read_text())
    require(vm['candidate_sha256'] == digest and vm['guard_stop_observed'] and not vm['kernel_reboot_command_observed'] and vm['timed_out'], 'Control VM guard failed')
    stock = PROJECT / 'artifacts/stock-cph2493-August-eu-ota'
    cases = []
    for unlocked in ['1', '0']:
        process = subprocess.run([str(ROOT / 'tools/avb-host/avb-boot-model'), str(stock), str(folder / 'nord3-busybox-candidate.img'), '0', unlocked], capture_output=True, text=True, timeout=20)
        require(process.returncode == 0, 'Control AVB model failed')
        cases.append(json.loads(process.stdout))
    require(cases[0]['slot_data_returned'] and cases[0]['boot_partitions_loaded'] == 1 and not cases[1]['slot_data_returned'], 'Control policy mismatch')
    output = PROJECT / 'docs/boot-hold-control-validation.json'
    output.write_text(json.dumps(dict(passed=True, candidate_sha256=digest, only_changed_archive_entry='init', reboot_request_removed=True, vm_receipt=str(vm_paths[-1]), branch_fixture_receipt=str(fixture), avb_cases=cases, phone_contacted=False, hardware_causality_proven=False), indent=2) + '\n')
    print('Independent control validation passed:', output)


if __name__ == '__main__':
    main()
