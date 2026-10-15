"""Bounded passive USB observation before and during Lynx's BusyBox trial; no phone commands."""
import json
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parent.parent
output = ROOT / 'logs' / ('lynx-usb-observation-' + str(time.time_ns()) + '.json')
started = time.monotonic()
events = []
previous = None
while time.monotonic() - started < 180:
    result = subprocess.run(['lsusb'], capture_output=True, text=True, timeout=5)
    phones = [line for line in result.stdout.splitlines() if any(value in line.lower()
              for value in ('0e8d:201c', '22d9:0006', '0e8d:2000', '0e8d:2001', '1d6b:0104'))]
    serials = sorted(str(path) for path in Path('/sys/class/tty').glob('ttyACM*'))
    state = {'usb': phones, 'serial_devices': serials}
    if state != previous:
        event = {'elapsed_seconds': round(time.monotonic() - started, 2), **state}
        events.append(event)
        print(json.dumps(event), flush=True)
        previous = state
    output.write_text(json.dumps({'events': events, 'phone_commands_sent': False,
                                 'observation_complete': False}, indent=2) + '\n')
    if any('1d6b:0104' in line.lower() for line in phones) and serials:
        break
    time.sleep(0.25)
output.write_text(json.dumps({'events': events, 'phone_commands_sent': False,
                             'observation_complete': True,
                             'elapsed_seconds': round(time.monotonic() - started, 2)}, indent=2) + '\n')
print('Observation saved:', output, flush=True)
