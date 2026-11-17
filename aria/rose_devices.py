#!/usr/bin/python3
"""Read-only USB capability inventory for Rose on Syra."""
import json
from pathlib import Path
import shutil
import subprocess

expected = {'comfast_lolth': ('0bda', 'd723'), 'receiver': ('3151', '3020'),
            'microphone': ('2886', '001a')}
present = {}
for path in Path('/sys/bus/usb/devices').iterdir():
    try:
        ids = ((path/'idVendor').read_text().strip(), (path/'idProduct').read_text().strip())
    except OSError:
        continue
    for name, wanted in expected.items():
        if ids == wanted:
            drivers = []
            for interface in path.glob(path.name + ':*'):
                driver = interface/'driver'
                if driver.exists():
                    drivers.append(driver.resolve().name)
            present[name] = {'usb_id': ':'.join(ids), 'port': path.name, 'present': True,
                             'drivers': sorted(set(drivers))}
for name, ids in expected.items():
    if name not in present:
        present[name] = {'usb_id': ':'.join(ids), 'present': False}
tools = {name: shutil.which(name) is not None for name in ['arecord']}
services = {}
for name in ['bluetooth.service']:
    services[name] = subprocess.run(['systemctl', 'is-active', '--quiet', name]).returncode == 0
services['noobia-speech.service'] = subprocess.run(['systemctl', '--user', 'is-active', '--quiet', 'noobia-speech.service']).returncode == 0
print(json.dumps({'host': subprocess.check_output(['hostname'], text=True).strip(),
                  'usb': present, 'tools': tools, 'services': services}, indent=2))
