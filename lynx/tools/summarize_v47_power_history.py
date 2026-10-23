"""Capture and summarize Lynx's private read-only battery history."""

import csv
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import time

from lynx_wifi_v19_contact import ssh_command


ROOT = Path(__file__).resolve().parent.parent
IP = '192.168.100.8'
BOOT_ID = '9054078d-aafa-4abf-9600-5c70f8234360'
HEADER = ('boot_id', 'uptime_s', 'epoch_s', 'capacity_percent',
          'current_ma', 'battery_temp_mC', 'pack_voltage_mV')


def main():
    os.umask(0o077)
    out = ROOT / 'logs' / f'v47-power-history-summary-{time.time_ns()}'
    out.mkdir(mode=0o700)
    report = {'state': 'starting', 'boot_id': BOOT_ID, 'phone_ip': IP,
              'phone_writes': False}
    command = (
        'set -eu; '
        f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{BOOT_ID}"; '
        'test "$(readlink /proc/1/exe)" = /sbin/openrc-init; '
        'test "$(stat -c %a /var/log/lynx/power.csv)" = 600; '
        'cat /var/log/lynx/power.csv'
    )
    argv = ssh_command(IP, command)
    argv[-2:-2] = ['-p', '2222']
    try:
        run = subprocess.run(argv, capture_output=True, timeout=15)
        if run.returncode or len(run.stdout) > 262144:
            raise ValueError('Pinned SSH failed or CSV exceeded its rotation bound')
        (out / 'power.csv').write_bytes(run.stdout)
        (out / 'stderr').write_bytes(run.stderr)
        lines = run.stdout.splitlines()
        cleaned = []
        anomalies = []
        for number, line in enumerate(lines, 1):
            leading_nuls = len(line) - len(line.lstrip(b'\x00'))
            if leading_nuls:
                anomalies.append({'line': number, 'leading_nul_bytes': leading_nuls})
            line = line[leading_nuls:]
            if b'\x00' in line:
                raise ValueError('Embedded NUL in power-history field')
            cleaned.append(line)
        rows = list(csv.DictReader(io.StringIO(b'\n'.join(cleaned).decode())))
        if not rows or tuple(rows[0]) != HEADER:
            raise ValueError('Power history header or samples missing')
        parsed = []
        by_boot = {}
        for row in rows:
            boot = row['boot_id']
            if not re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', boot):
                raise ValueError('Invalid boot ID in power history')
            values = {key: int(row[key]) for key in HEADER[1:]}
            if not (0 <= values['capacity_percent'] <= 100 and
                    -32768 <= values['current_ma'] <= 32767 and
                    10000 <= values['battery_temp_mC'] <= 60000 and
                    5000 <= values['pack_voltage_mV'] <= 10000):
                raise ValueError('Out-of-range power history sample')
            if boot in by_boot and values['uptime_s'] < by_boot[boot][-1]['uptime_s']:
                raise ValueError('Uptime regressed within boot history')
            by_boot.setdefault(boot, []).append(values)
            parsed.append((boot, values))
        if parsed[-1][0] != BOOT_ID:
            raise ValueError('Latest power row is from a different boot')
        summaries = {}
        for boot, samples in by_boot.items():
            first, last = samples[0], samples[-1]
            summaries[boot] = {
                'samples': len(samples),
                'uptime_span_seconds': last['uptime_s'] - first['uptime_s'],
                'capacity_first_percent': first['capacity_percent'],
                'capacity_last_percent': last['capacity_percent'],
                'positive_current_samples': sum(x['current_ma'] > 0 for x in samples),
                'negative_current_samples': sum(x['current_ma'] < 0 for x in samples),
                'current_first_ma': first['current_ma'],
                'current_last_ma': last['current_ma'],
                'battery_temp_max_mC': max(x['battery_temp_mC'] for x in samples),
                'pack_voltage_last_mV': last['pack_voltage_mV'],
                'unsynchronized_clock_samples': sum(x['epoch_s'] < 1577836800
                                                    for x in samples),
            }
        report.update(state='v47-power-history-summarized-with-gap' if anomalies
                      else 'v47-power-history-summarized',
                      raw_sha256=hashlib.sha256(run.stdout).hexdigest(),
                      rows=len(rows), by_boot=summaries, anomalies=anomalies,
                      original_bytes_preserved=True)
    except Exception as exc:
        report.update(state='failed-or-incomplete', error=str(exc))
    report['finished_ns'] = time.time_ns()
    result = out / 'result.json'
    result.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'state': report['state'], 'result': str(result),
                      'current_boot': report.get('by_boot', {}).get(BOOT_ID)}))
    if report['state'] not in ('v47-power-history-summarized',
                               'v47-power-history-summarized-with-gap'):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
