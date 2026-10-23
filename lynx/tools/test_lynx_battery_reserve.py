"""Exercise the reserve guard without invoking a real shutdown."""

from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / 'linux-port/lynx-battery-reserve.sh'
TEXT = SOURCE.read_text()


def run_case(capacity, error, expect):
    with tempfile.TemporaryDirectory(prefix='lynx-reserve-', dir=ROOT / 'linux-port/artifacts') as temp:
        directory = Path(temp)
        sample = directory / 'battery_snapshot'
        sample.write_text(f'gauge_device_type=42495\ncapacity_percent={capacity}\ncapacity_error={error}\n')
        marker = directory / 'shutdown-reason'
        script = TEXT.replace('SOURCE=/sys/bus/i2c/devices/7-0055/battery_snapshot',
                              f'SOURCE={sample}')
        script = script.replace('STATE=/run/lynx/battery-reserve', f'STATE={directory}/state')
        script = script.replace('INTERVAL=30', 'INTERVAL=0')
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
        if error == 0:
            assert once.returncode == 0 and f'capacity_percent={capacity}' in once.stdout
        else:
            assert once.returncode != 0
        if expect is not None:
            watch = subprocess.run(['/bin/sh', str(path), '--watch'], capture_output=True,
                                   text=True, timeout=3)
            assert watch.returncode == 2 and marker.read_text().strip() == expect


def main():
    run_case(88, 0, None)
    run_case(21, 0, None)
    run_case(20, 0, 'low_capacity')
    run_case(0, 1, 'gauge_unavailable')
    print('lynx-battery-reserve fixture passed: healthy, boundary, repeated low, repeated error')


if __name__ == '__main__':
    main()
