#!/usr/bin/env python3
"""Persist low-overhead Nexus health samples across an abrupt reset."""

import json
import os
from pathlib import Path
import subprocess
import time


OUT = Path('/noobia/aria/logs/nexus-reset-monitor.jsonl')
SENSORS = {'k10temp': 'cpu_mC', 'nvme': 'nvme_mC', 'amdgpu': 'apu_mC'}


def read(path):
    try:
        return Path(path).read_text().strip()
    except OSError:
        return None


def sample():
    data = {'time': time.time(), 'boot_id': read('/proc/sys/kernel/random/boot_id'),
            'uptime_s': float(read('/proc/uptime').split()[0])}
    for path in Path('/sys/class/hwmon').glob('hwmon*'):
        name = SENSORS.get(read(path / 'name'))
        if name:
            value = read(path / 'temp1_input')
            data[name] = int(value) if value and value.lstrip('-').isdigit() else None
    try:
        result = subprocess.run(
            ['nvidia-smi', '--query-gpu=temperature.gpu,power.draw,utilization.gpu,memory.used',
             '--format=csv,noheader,nounits'], capture_output=True, text=True, timeout=3,
            check=True)
        data['gpu'] = result.stdout.strip().splitlines()[0].split(', ')
    except (OSError, subprocess.SubprocessError, IndexError):
        data['gpu'] = None
    try:
        apps = subprocess.run(
            ['nvidia-smi', '--query-compute-apps=pid,process_name,used_gpu_memory',
             '--format=csv,noheader,nounits'], capture_output=True, text=True, timeout=3,
            check=True)
        data['gpu_apps'] = [line.strip()[:160] for line in apps.stdout.splitlines()[:8]]
    except (OSError, subprocess.SubprocessError):
        data['gpu_apps'] = None
    mem = read('/proc/meminfo') or ''
    for line in mem.splitlines():
        if line.startswith(('MemAvailable:', 'SwapFree:')):
            key, value = line.split(':', 1)
            data[key + '_kB'] = int(value.strip().split()[0])
    return data


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open('a', buffering=1) as log:
        while True:
            record = sample()
            log.write(json.dumps(record, separators=(',', ':')) + '\n')
            os.fsync(log.fileno())
            time.sleep(5)


if __name__ == '__main__':
    main()
