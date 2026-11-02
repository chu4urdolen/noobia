#!/usr/bin/env python3
"""Save a read-only map of Lynx's live camera sensors and power suppliers."""

import json
import os
from pathlib import Path
import subprocess
import time

from lynx_wifi_v19_contact import ssh_command

ROOT = Path(__file__).resolve().parent.parent
REMOTE = r'''
import json
from pathlib import Path

base = Path('/sys/firmware/devicetree/base')
handles = {}
for item in base.rglob('phandle'):
    try:
        handles[int.from_bytes(item.read_bytes(), 'big')] = item.parent
    except OSError:
        pass

def text(path):
    try:
        return [x.decode(errors='replace') for x in path.read_bytes().split(b'\0') if x]
    except OSError:
        return []

nodes = []
for bus, name in [('i2c@11d01000', 'sensor2@1a'),
                  ('i2c@11d05000', 'sensor0@36'),
                  ('i2c@11d06000', 'sensor1@10'),
                  ('i2c@11d06000', 'sensor4@3d')]:
    node = base / bus / name
    info = {'path': str(node.relative_to(base)),
            'compatible': text(node / 'compatible'),
            'sensor_names': text(node / 'sensor-names'),
            'status': text(node / 'status'), 'supplies': {}}
    for supply in sorted(node.glob('*-supply')):
        raw = supply.read_bytes()
        phandle = int.from_bytes(raw[:4], 'big')
        target = handles.get(phandle)
        info['supplies'][supply.name] = {
            'phandle': phandle,
            'provider': str(target.relative_to(base)) if target else None,
            'compatible': text(target / 'compatible') if target else [],
            'status': text(target / 'status') if target else []}
    nodes.append(info)
print(json.dumps({'nodes': nodes}, sort_keys=True))
'''


def main():
    os.umask(0o077)
    args = ssh_command("192.168.100.107", "python3 -")
    args[-2:-2] = ["-p", "2222"]
    result = subprocess.run(args, input=REMOTE, capture_output=True, text=True,
                            timeout=30)
    if result.returncode:
        raise SystemExit(result.stderr.strip() or "camera DT read failed")
    report = json.loads(result.stdout)
    report.update(phone_partitions_written=False, phone_modules_loaded=False,
                  captured_ns=time.time_ns())
    path = ROOT / "logs" / f"camera-dt-{report['captured_ns']}.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"receipt": str(path), "nodes": len(report["nodes"])},
                     sort_keys=True))


if __name__ == "__main__":
    main()
