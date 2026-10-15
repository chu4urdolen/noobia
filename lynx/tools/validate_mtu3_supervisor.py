"""Independent stock-module supervisor image validation; no phone access."""
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
    folder = PROJECT / 'artifacts/busybox-mtu3-timed-supervisor'
    image = (folder / 'nord3-busybox-candidate.img').read_bytes()
    digest = hashlib.sha256(image).hexdigest()
    require(digest == 'adb55ffe21b8079c4e64a8eb48917c6566dcfd58763fa813bb10a635ad2b6b9a', 'Supervisor image changed')
    baseline = (PROJECT / 'artifacts/busybox-usb-module-checkpoints/with-mtu3/nord3-busybox-candidate.img').read_bytes()
    require(hashlib.sha256(baseline).hexdigest() == '5bb984899b19c9e739faa23aa9039374a5ad20ab99c10948d5d2b964da3616d6', 'Baseline changed')
    boot, oldboot = read_boot_v4(image), read_boot_v4(baseline)
    require(len(image) == 67108864 and boot['kernel'] == oldboot['kernel'], 'Kernel or geometry changed')
    entries, before = read_newc(decompress(boot['ramdisk'])), read_newc(decompress(oldboot['ramdisk']))
    require(entries.keys() == before.keys(), 'Archive membership changed')
    require([name for name in before if before[name] != entries[name]] == ['init', 'etc/lynx-checkpoint-modules.load'], 'Unrelated archive changes')
    source = (PROJECT / 'mtu3-timed-supervisor.sh').read_bytes()
    marker = b'log "CHECKPOINT_ALL_MODULES_LOADED; REQUESTING_ONE_RESTART2_BOOTLOADER"'
    expected_init = before['init']['data'].split(marker)[0] + source + b"\nlynx_mtu3_supervise || log 'SUPERVISOR_REFUSED_OR_FAILED'\nstop\n"
    require(entries['init']['data'] == expected_init == (folder / 'init-source').read_bytes(), 'Supervisor init changed')
    require(expected_init.count(b'/bin/boot-proof-reboot\n') == 1, 'More than one reset call')
    require(b'configfs' not in expected_init and b'usb_mode' not in expected_init, 'Unexpected USB setup')
    names = before['etc/lynx-checkpoint-modules.load']['data'].decode().splitlines()
    require(entries['etc/lynx-checkpoint-modules.load']['data'].decode().splitlines() == names[:-1] and names[-1]=='mtu3.ko', 'Prefix33 changed')
    require(hashlib.sha256(entries['lib/modules/mtu3.ko']['data']).hexdigest() == 'd3c59fa794a6e02f014dd0de660592bb66c9d7f8eb941c1d1183f8a3322bb467', 'MTU3 differs from stock')
    coverage = struct.unpack('!4sIIQQQ28x', baseline[-64:])[3]
    require(image[coverage:] == baseline[coverage:], 'Metadata tail changed')
    tests_path = ROOT / 'tools/test-artifacts/mtu3-supervisor-1791671516955331219/result.json'
    tests = json.loads(tests_path.read_text())
    require(tests['passed'] and len(tests['cases']) == 6 and tests['source_sha256'] == hashlib.sha256(source).hexdigest(), 'Supervisor fixtures failed or source changed')
    vms = sorted((PROJECT / 'artifacts').glob('emulated-mtu3-supervisor-*/result.json'))
    require(bool(vms), 'Supervisor VM evidence absent')
    vm = json.loads(vms[-1].read_text())
    require(vm['candidate_sha256'] == digest and vm['module_checkpoint_failure_guard_observed'] and not vm['kernel_reboot_command_observed'], 'VM refusal guard failed')
    model = ROOT / 'tools/avb-host/avb-boot-model'
    ref = json.loads((PROJECT / 'docs/avb-boot-model-results.json').read_text())
    require(hashlib.sha256(model.read_bytes()).hexdigest() == ref['binary_sha256'], 'AVB model changed')
    stock = PROJECT / 'artifacts/stock-cph2493-August-eu-ota'
    cases = []
    for unlocked in ['1', '0']:
        process = subprocess.run([str(model), str(stock), str(folder / 'nord3-busybox-candidate.img'), '0', unlocked], capture_output=True, text=True, timeout=20)
        require(process.returncode == 0, 'AVB model failed')
        cases.append(json.loads(process.stdout))
    require(cases[0]['slot_data_returned'] and cases[0]['boot_partitions_loaded']==1 and not cases[1]['slot_data_returned'], 'AVB policy mismatch')
    output = PROJECT / 'docs/mtu3-supervisor-validation.json'
    output.write_text(json.dumps(dict(passed=True, candidate_sha256=digest, all_module_bytes_unchanged_from_baseline=True, kernel_unchanged=True, supervisor_test_receipt=str(tests_path), vm_receipt=str(vms[-1]), avb_cases=cases, phone_contacted=False, hardware_beacon_proven=False, limits='Host fixture clock and exact-image VM guard checks do not emulate an MT6983 probe or guarantee the kernel can reboot during a blocked insertion.'), indent=2) + '\n')
    print('Supervisor independent checks passed:', output)


if __name__ == '__main__':
    main()
