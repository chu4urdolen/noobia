"""Exercise the OpenRC handoff safety gate against isolated fake sysfs/proc."""
import json
import os
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / 'linux-port/openrc-handoff-guard.sh'
OUT = ROOT / 'linux-port/artifacts' / f'openrc-handoff-guard-check-{time.time_ns()}'


def fixture(name, changes=None):
    folder = OUT / name
    run = folder / 'run/lynx'
    proc = folder / 'proc'
    sysroot = folder / 'sys'
    thermal = sysroot / 'class/thermal'
    run.mkdir(parents=True)
    proc.mkdir()
    thermal.mkdir(parents=True)
    (folder / 'etc/lynx').mkdir(parents=True)
    token = 'a' * 32
    (folder / 'etc/lynx/session-token').write_text(token + '\n')
    (sysroot / 'module/lynx_battery_monitor').mkdir(parents=True)
    gauge = sysroot / 'bus/i2c/devices/7-0055'
    gauge.mkdir(parents=True)
    (gauge / 'battery_snapshot').write_text('fixture\n')
    (run / 'host-confirmed').write_text(token + '\n')
    (run / 'openrc-handoff-ready').write_text(token + '\n')
    for filename, expected in (
        ('thermal-watch.pid', '/run/lynx/thermal-watch.sh'),
        ('battery-watch.pid', '/run/lynx/battery-watch.sh'),
        ('thermal-cooling-watch/pid', '/run/lynx/thermal-cooling-watch.sh'),
    ):
        p = run / filename
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text('RUNNER_PID\n')
    for name in ('thermal-watch.sh', 'battery-watch.sh', 'thermal-cooling-watch.sh'):
        (run / name).write_bytes((ROOT / 'linux-port' / name).read_bytes())
    (run / 'thermal-watch.ready').touch()
    (run / 'thermal-cooling-watch/ready').touch()
    (proc / 'uptime').write_text('100.00 500.00\n')
    (run / 'battery-last').write_text(
        'sample_uptime_seconds=95.00\n'
        'gauge_device_type=42495\n'
        'temperature_millidegrees_celsius=27000\n'
        'temperature_error=0\nvoltage_error=0\ncurrent_error=0\n'
        'capacity_percent=80\ncapacity_error=0\n'
    )
    for idx, kind, value in ((0, 'soc_max', 37000), (1, 'cpu_0', 38000), (2, 'cpu_1', 37500)):
        zone = thermal / f'thermal_zone{idx}'
        zone.mkdir()
        (zone / 'type').write_text(kind + '\n')
        (zone / 'temp').write_text(str(value) + '\n')
    for idx in range(3):
        dev = thermal / f'cooling_device{idx}'
        dev.mkdir()
        (dev / 'type').write_text(f'thermal-cpufreq-{idx}\n')
        (dev / 'cur_state').write_text('0\n')
    if changes:
        changes(folder, token)
    runner = folder / 'run-check.sh'
    runner.write_text(f'''#!/bin/sh
set -eu
. '{SOURCE}'
RUN='{run}'
SYS='{sysroot}'
THERMAL='{thermal}'
PROC='{proc}'
ETC='{folder / 'etc/lynx'}'
pid=$$
mkdir -p "$PROC/$pid"
for item in thermal-watch battery-watch thermal-cooling-watch; do :; done
printf '%s\\0' /run/lynx/thermal-watch.sh > "$PROC/$pid/cmdline"
printf '%s\\0' /run/lynx/battery-watch.sh >> "$PROC/$pid/cmdline"
printf '%s\\0' /run/lynx/thermal-cooling-watch.sh >> "$PROC/$pid/cmdline"
sed -i "s/RUNNER_PID/$pid/g" "$RUN/thermal-watch.pid" "$RUN/battery-watch.pid" "$RUN/thermal-cooling-watch/pid"
lynx_openrc_handoff_guard
''')
    runner.chmod(0o700)
    # Since one fake proc cmdline is shared by all three, all expected process
    # names are present as separate NUL-delimited arguments.
    return runner


def reject(name, change):
    runner = fixture(name, change)
    result = subprocess.run([str(runner)], text=True, capture_output=True, timeout=5)
    return result.returncode != 0 and 'OPENRC_HANDOFF_GUARD_PASS' not in result.stdout


def main():
    OUT.mkdir(parents=True)
    good = subprocess.run([str(fixture('valid'))], text=True, capture_output=True, timeout=5)
    cases = {
        'valid_fixture_passes': good.returncode == 0 and 'OPENRC_HANDOFF_GUARD_PASS' in good.stdout,
        'wrong_token_refused': reject('wrong-token', lambda f, t: (f / 'run/lynx/openrc-handoff-ready').write_text('b' * 32 + '\n')),
        'stale_battery_sample_refused': reject('stale-battery', lambda f, t: (f / 'run/lynx/battery-last').write_text((f / 'run/lynx/battery-last').read_text().replace('95.00', '80.00'))),
        'battery_gauge_error_refused': reject('battery-error', lambda f, t: (f / 'run/lynx/battery-last').write_text((f / 'run/lynx/battery-last').read_text().replace('temperature_error=0', 'temperature_error=1'))),
        'hot_battery_refused': reject('hot-battery', lambda f, t: (f / 'run/lynx/battery-last').write_text((f / 'run/lynx/battery-last').read_text().replace('27000', '35000'))),
        'hot_cpu_refused': reject('hot-cpu', lambda f, t: (f / 'sys/class/thermal/thermal_zone1/temp').write_text('40000\n')),
        'missing_cpu_sensor_refused': reject('missing-sensor', lambda f, t: (f / 'sys/class/thermal/thermal_zone2').rename(f / 'sys/class/thermal/ignored_zone2')),
        'missing_cooling_control_refused': reject('missing-cooling', lambda f, t: (f / 'sys/class/thermal/cooling_device2').rename(f / 'sys/class/thermal/ignored_cooling2')),
        'missing_watcher_ready_refused': reject('missing-ready', lambda f, t: (f / 'run/lynx/thermal-watch.ready').unlink()),
    }
    report = {'state': 'openrc-handoff-guard-tests-passed' if all(cases.values()) else 'failed',
              'created_ns': time.time_ns(), 'source_sha256': __import__('hashlib').sha256(SOURCE.read_bytes()).hexdigest(),
              'checks': cases, 'valid_stdout': good.stdout, 'valid_stderr': good.stderr,
              'phone_contacted': False, 'phone_boot_or_partition_changed': False}
    (OUT / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    if not all(cases.values()):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
