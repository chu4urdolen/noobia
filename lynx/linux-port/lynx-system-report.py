"""Small native userspace report; known proc/sys files only, no device writes."""
import json
import os
import platform
from pathlib import Path


def read(path):
    return Path(path).read_text().strip()


report = {
    'architecture': platform.machine(),
    'kernel': platform.release(),
    'python': platform.python_version(),
    'boot_id': read('/proc/sys/kernel/random/boot_id'),
    'uptime_seconds': float(read('/proc/uptime').split()[0]),
    'cpu_online': read('/sys/devices/system/cpu/online'),
    'wifi_operstate': read('/sys/class/net/wlan0/operstate'),
    'memory_kib': {line.split(':', 1)[0]: int(line.split()[1])
                   for line in read('/proc/meminfo').splitlines()
                   if line.split(':', 1)[0] in {'MemTotal', 'MemAvailable', 'SwapTotal'}},
    'proc_readonly': bool(os.statvfs('/proc').f_flag & os.ST_RDONLY),
    'sys_readonly': bool(os.statvfs('/sys').f_flag & os.ST_RDONLY),
}
print(json.dumps(report, indent=2))
