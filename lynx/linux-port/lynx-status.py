#!/usr/bin/python3
"""Read-only, compact local health and access snapshot for Lynx Alpine."""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys


SERVICES = (
    'lynx-health', 'lynx-battery-reserve', 'lynx-local-logs', 'lynx-wifi',
    'lynx-dropbear', 'lynx-maintenance', 'lynx-time-sync',
    'lynx-power-history',
)
GAUGE = Path('/sys/bus/i2c/devices/7-0055/battery_snapshot')


def read(path):
    try:
        return Path(path).read_text(errors='replace')[:4096].strip()
    except OSError:
        return None


def integer(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def command(*argv):
    try:
        result = subprocess.run(argv, capture_output=True, text=True,
                                timeout=3, check=False)
        return result.returncode, result.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return None, ''


def snapshot():
    issues = []
    gauge = {}
    raw = read(GAUGE)
    if raw:
        for line in raw.splitlines():
            if '=' in line:
                key, value = line.split('=', 1)
                gauge[key] = value
    battery = {
        'capacity_percent': integer(gauge.get('capacity_percent')),
        'temperature_mC': integer(gauge.get('temperature_millidegrees_celsius')),
        'current_mA_signed': integer(gauge.get('gauge_current_ma_signed')),
        'voltage_mV': integer(gauge.get('pack_voltage_mv')),
        'gauge_type': integer(gauge.get('gauge_device_type')),
        'read_errors': {name: integer(gauge.get(name + '_error')) for name in
                        ('capacity', 'temperature', 'current', 'voltage')},
    }
    if battery['gauge_type'] != 42495 or any(
            value != 0 for value in battery['read_errors'].values()):
        issues.append('battery_gauge_unavailable')
    cap = battery['capacity_percent']
    temp = battery['temperature_mC']
    if cap is None or not 0 <= cap <= 100:
        issues.append('battery_capacity_invalid')
    elif cap <= 20:
        issues.append('battery_at_reserve')
    if temp is None or not 0 < temp < 60000:
        issues.append('battery_temperature_invalid')
    elif temp >= 40000:
        issues.append('battery_warm')

    thermal = {}
    for zone in sorted(Path('/sys/class/thermal').glob('thermal_zone*')):
        name = read(zone / 'type')
        if name and (name.startswith('cpu_') or name == 'soc_max'):
            thermal[name] = integer(read(zone / 'temp'))
    valid_temps = [value for value in thermal.values() if value is not None]
    thermal_max = max(valid_temps, default=None)
    if thermal_max is None:
        issues.append('thermal_unavailable')
    elif thermal_max >= 55000:
        issues.append('thermal_hot')
    cooling = {}
    for dev in sorted(Path('/sys/class/thermal').glob('cooling_device*')):
        name = read(dev / 'type')
        if name and name.startswith('thermal-cpufreq-'):
            cooling[name] = integer(read(dev / 'cur_state'))

    services = {}
    for name in SERVICES:
        code, _ = command('/sbin/rc-service', name, 'status')
        services[name] = code == 0
        if code != 0:
            issues.append('service_' + name)

    carrier = read('/sys/class/net/wlan0/carrier')
    code, ip_output = command('ip', '-4', '-o', 'addr', 'show', 'dev', 'wlan0')
    match = re.search(r'\binet\s+(\d+\.\d+\.\d+\.\d+/\d+)', ip_output)
    ip_address = match.group(1) if code == 0 and match else None
    if carrier != '1' or ip_address is None:
        issues.append('wifi_unavailable')

    root_source = None
    root_type = None
    mounts = read('/proc/mounts')
    if mounts:
        for line in mounts.splitlines():
            fields = line.split()
            if len(fields) >= 3 and fields[1] == '/':
                root_source, root_type = fields[0], fields[2]
                break
    if root_type != 'ext4' or not root_source:
        issues.append('root_filesystem_unexpected')
    ext4_errors = None
    if root_type == 'ext4' and root_source:
        ext4_errors = integer(read('/sys/fs/ext4/' + Path(root_source).name +
                                   '/errors_count'))
        if ext4_errors is None:
            issues.append('ext4_error_counter_unavailable')
        elif ext4_errors != 0:
            issues.append('ext4_errors_recorded')
    filesystem = os.statvfs('/')
    free_mib = filesystem.f_bavail * filesystem.f_frsize // (1024 * 1024)
    if free_mib < 350:
        issues.append('root_space_low')
    try:
        power_log_bytes = Path('/var/log/lynx/power.csv').stat().st_size
    except OSError:
        power_log_bytes = None
        issues.append('power_log_missing')

    uptime_raw = read('/proc/uptime')
    try:
        uptime_seconds = int(float(uptime_raw.split()[0]))
    except (AttributeError, ValueError, IndexError):
        uptime_seconds = None
    return {
        'schema': 2,
        'boot_id': read('/proc/sys/kernel/random/boot_id'),
        'uptime_seconds': uptime_seconds,
        'alpine_release': read('/etc/alpine-release'),
        'battery': battery,
        'thermal': {'max_mC': thermal_max, 'zones_mC': thermal,
                    'cooling_states': cooling},
        'services_running': services,
        'wifi': {'carrier': carrier == '1', 'ipv4': ip_address},
        'root_free_mib': free_mib,
        'root_filesystem': {'source': root_source, 'type': root_type,
                            'ext4_errors_count': ext4_errors},
        'power_log_bytes': power_log_bytes,
        'issues': issues,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--assert-ready', action='store_true',
                        help='exit nonzero if the snapshot has an issue')
    args = parser.parse_args()
    state = snapshot()
    print(json.dumps(state, sort_keys=True, separators=(',', ':')))
    return 1 if args.assert_ready and state['issues'] else 0


if __name__ == '__main__':
    sys.exit(main())
