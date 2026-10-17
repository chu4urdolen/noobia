"""Exercise Lynx's exact health checks and fail-safe loop with fake devices."""
import json
import os
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / 'linux-port/lynx-health-supervisor.sh'


def main():
    os.umask(0o077)
    out = ROOT / 'linux-port/artifacts' / ('health-supervisor-check-' + str(time.time_ns()))
    out.mkdir(mode=0o700)
    run = out / 'run'
    thermal = out / 'thermal'
    proc = out / 'proc'
    gauge = out / 'gauge'
    run.mkdir()
    thermal.mkdir()
    proc.mkdir()
    gauge.write_text('available\n')
    (proc / 'uptime').write_text('100.00 10.00\n')

    def snapshot(sample=98, battery=27000, capacity=77):
        (run / 'battery-last').write_text(
            f'sample_uptime_seconds={sample}.00\n'
            'gauge_device_type=42495\n'
            f'temperature_millidegrees_celsius={battery}\n'
            f'capacity_percent={capacity}\n'
            'temperature_error=0\nvoltage_error=0\ncurrent_error=0\ncapacity_error=0\n')

    snapshot()
    for name, kind, value in [('thermal_zone0', 'soc_max', 32000),
                              ('thermal_zone1', 'cpu_0', 33000),
                              ('thermal_zone2', 'cpu_1', 34000)]:
        device = thermal / name
        device.mkdir()
        (device / 'type').write_text(kind + '\n')
        (device / 'temp').write_text(str(value) + '\n')
    for index in range(3):
        device = thermal / f'cooling_device{index}'
        device.mkdir()
        (device / 'type').write_text(f'thermal-cpufreq-{index}\n')
        (device / 'cur_state').write_text('0\n')

    original = SOURCE.read_text()
    marker = '\ncase "${1:-}" in\n'
    assert original.count(marker) == 1
    fake = (original.replace('RUN=/run/lynx', f'RUN={run}')
                    .replace('PROC=/proc', f'PROC={proc}')
                    .replace('THERMAL=/sys/class/thermal', f'THERMAL={thermal}')
                    .replace('/sys/bus/i2c/devices/7-0055/battery_snapshot', str(gauge))
                    .replace(marker, '\nrequire_process() { return 0; }\n' + marker))
    script = out / 'health-fixture.sh'
    script.write_text(fake)

    def once(label):
        result = subprocess.run(['/bin/sh', str(script), '--once'], capture_output=True, timeout=5)
        (out / (label + '.stdout')).write_bytes(result.stdout)
        (out / (label + '.stderr')).write_bytes(result.stderr)
        return result.returncode == 0 and b'LYNX_HEALTH_OK' in result.stdout

    checks = {'normal-sensors-accepted': once('normal')}
    snapshot(sample=80)
    checks['stale-battery-refused'] = not once('stale')
    snapshot(battery=45000)
    checks['hot-battery-refused'] = not once('battery-hot')
    snapshot()
    (thermal / 'thermal_zone1/temp').write_text('46000\n')
    checks['missing-cooling-at-46c-refused'] = not once('cooling-missing')
    for index in range(3):
        (thermal / f'cooling_device{index}/cur_state').write_text('1\n')
    checks['applied-cooling-at-46c-accepted'] = once('cooling-applied')
    (thermal / 'thermal_zone2/type').write_text('irrelevant\n')
    checks['missing-second-cpu-sensor-refused'] = not once('cpu-missing')

    # Override only the sampler for this control-flow check. The exact source
    # loop still counts failures and chooses the fake power command.
    fake_bb = out / 'fake-busybox'
    fake_bb.write_text('#!/bin/sh\ncase "$1" in sleep) exit 0;; poweroff) echo requested >> "' +
                       str(out / 'poweroff-requested') + '"; exit 0;; *) exit 90;; esac\n')
    fake_bb.chmod(0o700)
    watch = (fake.replace('BB=/bin/busybox', f'BB={fake_bb}')
                 .replace('echo \'<2>LYNX_HEALTH_SAFE_POWEROFF\' > /dev/kmsg',
                          f'echo \'<2>LYNX_HEALTH_SAFE_POWEROFF\' > {out / "fake-kmsg"}')
                 .replace(marker, '\nhealth_once() { echo FIXTURE_BAD_SENSOR; return 1; }\n' + marker))
    watch_script = out / 'watch-fixture.sh'
    watch_script.write_text(watch)
    result = subprocess.run(['/bin/sh', str(watch_script), '--watch'], capture_output=True, timeout=5)
    events = (run / 'health-supervisor/events.log').read_text()
    checks['three-failures-request-one-safe-poweroff'] = (
        result.returncode == 2 and (out / 'poweroff-requested').read_text().count('requested') == 1
        and events.count('LYNX_HEALTH_FAILURE') == 3 and 'LYNX_HEALTH_SAFE_POWEROFF' in events)
    report = {'passed': all(checks.values()), 'checks': checks,
              'phone_contacted': False, 'real_power_command_issued': False,
              'limits': 'Synthetic sysfs/process fixtures and fake poweroff. Live --once is separately verified; live continuous mode is not proven by this test.'}
    (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'passed': report['passed'], 'result': str(out / 'result.json'), 'checks': checks}))
    if not report['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
