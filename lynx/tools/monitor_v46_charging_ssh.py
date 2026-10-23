"""Bounded, read-only pinned SSH watch for Lynx during a charger trial."""

import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from capture_v34_health_window import matching_host, open_ssh_hosts
from lynx_wifi_v19_contact import ssh_command


ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / 'linux-port/artifacts/persistent-alpine-v46-offline/build-result.json'
COMMAND = (
    "printf 'INIT_SHA '; sha256sum /init; "
    "printf 'BOOT_ID '; cat /proc/sys/kernel/random/boot_id; "
    "printf 'PID1 '; readlink -f /proc/1/exe; "
    "printf 'BATTERY_BEGIN\\n'; cat /sys/bus/i2c/devices/7-0055/battery_snapshot 2>/dev/null; "
    "printf 'BATTERY_END\\n'; "
    "for d in /sys/class/power_supply/*; do "
    "[ -r \"$d/online\" ] || continue; "
    "printf 'SUPPLY %s online=%s status=%s\\n' \"${d##*/}\" "
    "\"$(cat \"$d/online\")\" \"$(cat \"$d/status\" 2>/dev/null)\"; done; "
    "true"
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds', type=int, default=240)
    args = parser.parse_args()
    if not 30 <= args.seconds <= 360:
        parser.error('--seconds must be 30..360')
    expected = json.loads(BUILD.read_text())['init_sha256']
    os.umask(0o077)
    out = ROOT / 'logs' / f'v46-charging-ssh-watch-{time.time_ns()}'
    out.mkdir(mode=0o700)
    receipt = out / 'result.json'
    report = {'state': 'watching', 'started_ns': time.time_ns(),
              'seconds': args.seconds, 'phone_writes': False,
              'expected_init_sha256': expected, 'samples': []}

    def save():
        tmp = receipt.with_suffix('.tmp')
        tmp.write_text(json.dumps(report, indent=2) + '\n')
        tmp.replace(receipt)

    save()
    start = time.monotonic()
    while time.monotonic() - start < args.seconds:
        ip = matching_host(asyncio.run(open_ssh_hosts()))
        if ip is None:
            time.sleep(5)
            continue
        sample = {'ip': ip, 'started_ns': time.time_ns()}
        try:
            run = subprocess.run(ssh_command(ip, COMMAND), capture_output=True,
                                 timeout=12)
        except subprocess.TimeoutExpired as error:
            sample.update(timed_out=True)
            raw = (error.stdout or b'') + (error.stderr or b'')
            (out / f'sample-{len(report["samples"])+1}.raw').write_bytes(raw)
            sample.update(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
            report['samples'].append(sample)
            save()
            time.sleep(5)
            continue
        raw = run.stdout + run.stderr
        path = out / f'sample-{len(report["samples"])+1}.raw'
        path.write_bytes(raw)
        sample.update(exit_code=run.returncode,
                      bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(),
                      exact_v46=(expected.encode() + b'  /init') in run.stdout,
                      battery_snapshot=b'capacity_percent=' in run.stdout)
        report['samples'].append(sample)
        save()
        if sample['exact_v46'] and sample['battery_snapshot'] and run.returncode == 0:
            report['state'] = 'exact-v46-battery-snapshot-observed'
            break
        time.sleep(5)
    if report['state'] == 'watching':
        report['state'] = 'pinned-ssh-not-observed-with-battery'
    report['finished_ns'] = time.time_ns()
    save()
    print(json.dumps({'state': report['state'], 'result': str(receipt),
                      'samples': len(report['samples'])}))


if __name__ == '__main__':
    main()
