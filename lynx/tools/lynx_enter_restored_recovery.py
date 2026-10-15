"""Fixed recovery reboot from the verified restored stock boot_a; no flash."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parent.parent
FASTBOOT = ROOT / 'tools/platform-tools/fastboot'
SERIAL = '89BYAY5L4T9HFUOV'
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--connect', action='store_true')
args = parser.parse_args()
command = [str(FASTBOOT), '-s', SERIAL, 'reboot', 'recovery']
if hashlib.sha256(FASTBOOT.read_bytes()).hexdigest() != 'a686e2c7e8dc9cf4cba0cb8a2eef05f7b2bd682c925abd032fe203215d80b618':
    raise RuntimeError('Fastboot changed')
restore = json.loads((ROOT / 'logs/boot-a-usb-device-mode-trial-1791645217241106203.json').read_text())
assert restore['mode'] == 'restore-stock' and len(restore['operations']) == 1
assert restore['operations'][0]['exit_code'] == 0 and restore['operations'][0]['command'][3:5] == ['flash', 'boot_a']
stock = ROOT / 'linux-port/artifacts/stock-cph2493-August-eu-ota/boot.img'
assert hashlib.sha256(stock.read_bytes()).hexdigest() == 'a67f03d7b826b834c23653b67eaa6efa971eb70ef8af19eee4d33fb5fc7fe995'
if not args.connect:
    print(json.dumps({'command': command, 'phone_contacted': False, 'partition_writes': False}, indent=2))
    raise SystemExit(0)
preflight = subprocess.run(['python3', str(ROOT / 'tools/lynx_fastboot_preflight.py'), '--connect'],
                           capture_output=True, text=True, timeout=120)
if preflight.returncode:
    raise RuntimeError('Fresh preflight failed; no reboot sent: ' + preflight.stdout)
receipt = {'command': command, 'phone_contacted': True, 'partition_writes': False,
           'preflight': json.loads(preflight.stdout), 'state': 'issued'}
path = ROOT / 'logs' / ('restored-recovery-entry-' + str(time.time_ns()) + '.json')
path.write_text(json.dumps(receipt, indent=2) + '\n')
try:
    result = subprocess.run(command, capture_output=True, text=True, timeout=15)
    receipt.update(state='returned', exit_code=result.returncode, output=result.stdout + result.stderr)
finally:
    path.write_text(json.dumps(receipt, indent=2) + '\n')
print(receipt['output'])
print('Receipt:', path)
raise SystemExit(result.returncode)
