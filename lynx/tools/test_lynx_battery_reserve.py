"""Exercise the reserve guard without invoking a real shutdown."""

from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / 'linux-port/lynx-battery-reserve.sh'
TEXT = SOURCE.read_text()


def run_case(capacity, error, expect, *, current=-91, current_error=0,
             temperature=25000, temperature_error=0, charging_hold=False,
             no_progress=False):
    with tempfile.TemporaryDirectory(prefix='lynx-reserve-', dir=ROOT / 'linux-port/artifacts') as temp:
        directory = Path(temp)
        sample = directory / 'battery_snapshot'
        sample.write_text(
            f'gauge_device_type=42495\ncapacity_percent={capacity}\n'
            f'capacity_error={error}\ngauge_current_ma_signed={current}\n'
            f'current_error={current_error}\n'
            f'temperature_millidegrees_celsius={temperature}\n'
            f'temperature_error={temperature_error}\n')
        marker = directory / 'shutdown-reason'
        script = TEXT.replace('SOURCE=/sys/bus/i2c/devices/7-0055/battery_snapshot',
                              f'SOURCE={sample}')
        script = script.replace('STATE=/run/lynx/battery-reserve', f'STATE={directory}/state')
        script = script.replace('INTERVAL=30',
                                'INTERVAL=1' if charging_hold else 'INTERVAL=0')
        if no_progress:
            script = script.replace('MAX_HOLD_SAMPLES=240', 'MAX_HOLD_SAMPLES=2')
        script = script.replace('[ -d /run/lynx ] || exit 1', f'[ -d {directory} ] || exit 1')
        begin = script.index('request_shutdown() {')
        end = script.index('\n}\n\ncase ', begin) + 2
        script = (script[:begin] + 'request_shutdown() {\n'
                  f'    printf "%s\\n" "$1" > {marker}\n'
                  '    exit 2\n}\n' + script[end:])
        assert '/sbin/openrc-shutdown' not in script and '/dev/kmsg' not in script
        path = directory / 'guard.sh'
        path.write_text(script)
        once = subprocess.run(['/bin/sh', str(path), '--once'], capture_output=True,
                              text=True, timeout=3)
        if error == current_error == temperature_error == 0:
            assert once.returncode == 0 and f'capacity_percent={capacity}' in once.stdout
        else:
            assert once.returncode != 0
        if charging_hold:
            assert expect is None
            try:
                subprocess.run(['/bin/sh', str(path), '--watch'], capture_output=True,
                               text=True, timeout=2.3)
                raise AssertionError('Charging watch unexpectedly exited')
            except subprocess.TimeoutExpired as watch:
                assert b'LYNX_BATTERY_RESERVE_CHARGING' in (watch.stdout or b'')
                assert not marker.exists()
        elif expect is not None:
            watch = subprocess.run(['/bin/sh', str(path), '--watch'], capture_output=True,
                                   text=True, timeout=3)
            assert watch.returncode == 2 and marker.read_text().strip() == expect


def main():
    run_case(88, 0, None)
    run_case(21, 0, None)
    run_case(20, 0, 'low_capacity')
    run_case(20, 0, None, current=130, charging_hold=True)
    run_case(20, 0, 'no_charge_progress', current=130, no_progress=True)
    run_case(20, 0, 'low_capacity', current=49)
    run_case(10, 0, 'critical_capacity', current=130)
    run_case(20, 0, 'charging_temperature', current=130, temperature=40000)
    run_case(20, 0, 'gauge_unavailable', current_error=1)
    run_case(0, 1, 'gauge_unavailable')
    print('lynx-battery-reserve fixture passed: low, charging hold, critical, hot, invalid gauge')


if __name__ == '__main__':
    main()
