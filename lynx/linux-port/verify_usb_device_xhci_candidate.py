"""Record exact-image VM and AVB-model evidence; no device access or writes."""
import hashlib
import json
from pathlib import Path
import re
import subprocess

BASE = Path(__file__).resolve().parent
CANDIDATE = BASE / 'artifacts/busybox-August-usb-device-xhci'
STOCK = BASE / 'artifacts/stock-cph2493-August-eu-ota'
image = CANDIDATE / 'nord3-busybox-candidate.img'
digest = hashlib.sha256(image.read_bytes()).hexdigest()
report_path = CANDIDATE / 'build-validation.json'
report = json.loads(report_path.read_text())
vm = json.loads((BASE / 'artifacts/emulated-usb-device-xhci/result.json').read_text())
assert digest == report['candidate_sha256'] == vm['candidate_sha256']
assert vm['native_pid1_marker_observed'] and vm['interactive_commands_executed']
assert vm['pid1_comm'] == 'init' and vm['qemu_exit_code'] == 0
assert 'noobia.usb=1' not in vm['command'][-1]
console = (BASE / 'artifacts/emulated-usb-device-xhci/console.log').read_text()
loaded = re.findall(r'noobia-init: Loaded (\S+)', console)
assert loaded == report['usb_module_load_order'] and len(loaded) == 35
assert not any(value in console for value in ['Module failed', 'Unknown symbol', 'syntax error'])
guards = json.loads((BASE / 'docs/usb-device-xhci-guard-tests.json').read_text())
assert guards['helper_sha256'] == hashlib.sha256((BASE / 'usb-device-mode-xhci.sh').read_bytes()).hexdigest()
assert len(guards['cases']) == 13 and all(case['passed'] for case in guards['cases'])
init = (BASE / report['native_init_source']).read_bytes()
assert init.count((BASE / 'usb-device-mode-xhci.sh').read_bytes()) == 1
assert report['native_init_sha256'] == hashlib.sha256(init).hexdigest()
report.update(init_syntax_checked_by_target_busybox=True, init_arm64_validation_pending=False,
              init_validation_method='Exact stock kernel and vendor-before-generic ramdisk executed in isolated QEMU ARM64',
              hardware_boot_proven=False)
report_path.write_text(json.dumps(report, indent=2) + '\n')
proof = {'candidate_sha256': digest, 'native_init_sha256': report['native_init_sha256'],
         'all_35_modules_loaded_without_custom_argument': True, 'interactive_shell_executed': True,
         'helper_guard_cases_passed': 13, 'phone_contacted': False, 'physical_usb_binding_proven': False}
(BASE / 'docs/usb-device-xhci-arm64-validation.json').write_text(json.dumps(proof, indent=2) + '\n')
binary = BASE.parent / 'tools/avb-host/avb-boot-model'
old_model = json.loads((BASE / 'docs/always-usb-avb-model.json').read_text())
cases = []
for unlocked in [1, 0]:
    run = subprocess.run([str(binary), str(STOCK), str(image), '0', str(unlocked)], capture_output=True, text=True, timeout=15)
    assert run.returncode == 0
    value = json.loads(run.stdout)
    assert value['result'] == 'ERROR_VERIFICATION'
    assert value['boot_partitions_loaded'] == unlocked and value['slot_data_returned'] == bool(unlocked)
    value.update(case='usb_device_xhci_' + ('unlocked' if unlocked else 'locked'),
                 image_sha256=digest, diagnostics=run.stderr)
    cases.append(value)
(BASE / 'docs/usb-device-xhci-avb-model.json').write_text(json.dumps({
    'candidate_sha256': digest, 'model_binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(),
    'cases': cases, 'phone_contacted': False, 'limits': old_model['limits']}, indent=2) + '\n')
subprocess.run(['python3', str(BASE / 'validate_image.py'), '--directory', str(CANDIDATE),
                '--stock-boot', str(STOCK / 'boot.img'),
                '--vendor-ramdisk', str(STOCK / 'unpacked-vendor-boot/vendor_ramdisk00')], check=True, timeout=30)
print(json.dumps(proof, indent=2))
