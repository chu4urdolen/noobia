"""Exercise the native role helper against fake sysfs only; never touch USB."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

from audit_early_boot import read_fdt, strings

BASE = Path(__file__).resolve().parent
STOCK = BASE / 'artifacts/stock-cph2493-August-eu-ota'
HELPER = BASE / 'usb-device-mode.sh'
nodes, _ = read_fdt((STOCK / 'unpacked-vendor-boot/dtb').read_bytes())
props = nodes['/soc/usb0@11201000']
assert 'mediatek,mtu3' in strings(props['compatible'])
assert strings(props['dr_mode']) == ['otg']
assert 'usb-role-switch' in props and 'enable-manual-drd' not in props
module = (STOCK / 'vendor-ramdisk-unpacked/lib/modules/mtu3.ko').read_bytes()
assert all(value in module for value in [b'mode_store\0', b'ssusb_role_sw_set\0', b'store mode %d op_mode %d'])
busybox = shutil.which('busybox')
assert busybox, 'Offline helper test needs host BusyBox'
cases = []
for case in ['qualified', 'unbound', 'wrong-driver', 'wrong-compatible', 'manual-drd',
             'no-role-property', 'no-registered-switch', 'wrong-role-parent',
             'wrong-port', 'not-otg', 'invalid-mode', 'already-device']:
    with tempfile.TemporaryDirectory(prefix='usb-role-fixture-', dir=BASE / 'artifacts') as folder:
        root = Path(folder)
        controller = root / 'bus/platform/devices' / ('11211000.usb0' if case == 'wrong-port' else '11201000.usb0')
        node = controller / 'of_node'
        node.mkdir(parents=True)
        driver = root / 'bus/platform/drivers' / ('other' if case == 'wrong-driver' else 'mtu3')
        driver.mkdir(parents=True)
        if case != 'unbound':
            (controller / 'driver').symlink_to(driver)
        (node / 'compatible').write_bytes(b'other\0' if case == 'wrong-compatible' else props['compatible'])
        (node / 'dr_mode').write_bytes(b'host\0' if case == 'not-otg' else props['dr_mode'])
        if case != 'no-role-property':
            (node / 'usb-role-switch').touch()
        if case == 'manual-drd':
            (node / 'enable-manual-drd').touch()
        if case != 'no-registered-switch':
            role = root / 'class/usb_role/11201000.usb0-role-switch'
            role.mkdir(parents=True)
            (role / 'device').symlink_to(root if case == 'wrong-role-parent' else controller)
        mode = controller / 'mode'
        before = 'invalid\n' if case == 'invalid-mode' else ('3\n' if case == 'already-device' else '1\n')
        mode.write_text(before)
        script = 'BB="$1"; SYS_ROOT="$2"; log() { printf "%s\\n" "$*"; }; . "$3"; lynx_usb_device_mode; lynx_usb_device_mode'
        run = subprocess.run([busybox, 'sh', '-c', script, 'fixture', busybox, str(root), str(HELPER)], capture_output=True, text=True, timeout=5)
        assert run.returncode == 0, run.stderr
        expected = '3\n' if case in ('qualified', 'already-device') else before
        assert mode.read_text() == expected, case
        assert run.stdout.count('peripheral mode requested') == (1 if case in ('qualified', 'already-device') else 0), case
        cases.append({'case': case, 'passed': True})
report = {'helper_sha256': hashlib.sha256(HELPER.read_bytes()).hexdigest(),
          'stock_mtu3_sha256': hashlib.sha256(module).hexdigest(), 'stock_base_dtb_guards_passed': True,
          'cases': cases, 'phone_contacted': False, 'physical_role_switch_proven': False,
          'limits': 'Base DTB and binary symbol/string evidence; selected runtime DTBO and exact driver behavior remain unobserved.'}
(BASE / 'docs/usb-device-mode-guard-tests.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
