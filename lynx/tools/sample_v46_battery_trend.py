"""Take bounded read-only battery/current samples on the same pinned V46 boot."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time

from lynx_wifi_v19_contact import ssh_command


ROOT = Path(__file__).resolve().parent.parent
BOOT_ID = re.compile(rb'(?m)^BOOT_ID ([0-9a-f-]{36})$')
COMMAND = (
    "printf 'BOOT_ID '; cat /proc/sys/kernel/random/boot_id; "
    "printf 'BATTERY_BEGIN\\n'; "
    "cat /sys/bus/i2c/devices/7-0055/battery_snapshot; "
    "printf 'BATTERY_END\\n'; "
    "for d in /sys/class/power_supply/*; do "
    "[ -r \"$d/online\" ] || continue; "
    "printf 'SUPPLY %s online=%s status=%s\\n' \"${d##*/}\" "
    "\"$(cat \"$d/online\")\" \"$(cat \"$d/status\" 2>/dev/null)\"; done"
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--watch-result', required=True, type=Path)
    parser.add_argument('--count', type=int, default=5)
    parser.add_argument('--interval', type=int, default=10)
    args = parser.parse_args()
    if not 2 <= args.count <= 10 or not 5 <= args.interval <= 30:
        parser.error('Use 2..10 samples at 5..30-second intervals')
    source = args.watch_result.resolve(strict=True)
    if not source.is_relative_to(ROOT / 'logs'):
        raise ValueError('Watch receipt outside Lynx logs')
    watch = json.loads(source.read_text())
    if watch.get('state') != 'exact-v46-battery-snapshot-observed':
        raise ValueError('Exact V46 pinned battery snapshot missing')
    index = len(watch['samples'])
    first = source.parent / f'sample-{index}.raw'
    first_raw = first.read_bytes()
    if hashlib.sha256(first_raw).hexdigest() != watch['samples'][-1]['sha256']:
        raise ValueError('Pinned snapshot hash differs')
    match = BOOT_ID.search(first_raw)
    if not match:
        raise ValueError('Boot ID missing')
    boot_id = match.group(1).decode()
    ip = watch['samples'][-1]['ip']
    if not re.fullmatch(r'192\.168\.100\.[1-9][0-9]?', ip):
        raise ValueError('Unrecognized pinned address')

    os.umask(0o077)
    out = ROOT / 'logs' / f'v46-battery-trend-{time.time_ns()}'
    out.mkdir(mode=0o700)
    receipt = out / 'result.json'
    report = {'state': 'sampling', 'watch_result': str(source),
              'boot_id': boot_id, 'phone_ip': ip, 'phone_writes': False,
              'started_ns': time.time_ns(), 'samples': []}

    def save():
        temp = receipt.with_suffix('.tmp')
        temp.write_text(json.dumps(report, indent=2) + '\n')
        temp.replace(receipt)

    save()
    for number in range(1, args.count + 1):
        try:
            run = subprocess.run(ssh_command(ip, COMMAND), capture_output=True, timeout=12)
            raw = run.stdout + run.stderr
            (out / f'sample-{number}.raw').write_bytes(raw)
            fields = dict(re.findall(r'(?m)^([a-z_]+)=([^\r\n]*)$',
                                     run.stdout.decode(errors='replace')))
            same_boot = f'BOOT_ID {boot_id}\n'.encode() in run.stdout
            item = {'number': number, 'sampled_ns': time.time_ns(),
                    'exit_code': run.returncode,
                    'same_boot': same_boot,
                    'sha256': hashlib.sha256(raw).hexdigest(),
                    'capacity_percent': fields.get('capacity_percent'),
                    'gauge_current_ma_signed': fields.get('gauge_current_ma_signed'),
                    'temperature_millidegrees_celsius':
                        fields.get('temperature_millidegrees_celsius')}
            report['samples'].append(item)
            save()
            if run.returncode or not same_boot or item['gauge_current_ma_signed'] is None:
                report['state'] = 'contact-lost-or-invalid'
                break
            if number < args.count:
                time.sleep(args.interval)
        except Exception as error:
            report['state'] = 'contact-lost-or-invalid'
            report['error'] = str(error)
            break
    else:
        report['state'] = 'same-boot-trend-captured'
    report['finished_ns'] = time.time_ns()
    save()
    print(json.dumps({'state': report['state'], 'result': str(receipt),
                      'samples': report['samples']}))


if __name__ == '__main__':
    main()
