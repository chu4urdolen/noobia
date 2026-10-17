"""Exercise the inert health startup's process order with fake hardware only."""
import hashlib
import json
import os
import re
import signal
import subprocess
import tarfile
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PORT = ROOT / 'linux-port'
SOURCE = PORT / 'autonomous-health-start.sh'
ARCHIVE = PORT / 'artifacts/autonomous-health-inputs/inputs.tar.gz'


def main():
    os.umask(0o077)
    with tempfile.TemporaryDirectory(prefix='lynx-health-start-', dir=PORT / 'artifacts') as temp:
        base = Path(temp)
        run = base / 'run/lynx'
        run.mkdir(parents=True)
        sys = base / 'sys'
        (sys / 'module').mkdir(parents=True)
        for index, (name, value) in enumerate([('cpu_0', 31000), ('cpu_1', 32000), ('soc_max', 33000)]):
            zone = sys / 'class/thermal' / ('thermal_zone' + str(index))
            zone.mkdir(parents=True)
            (zone / 'type').write_text(name + '\n')
            (zone / 'temp').write_text(str(value) + '\n')
        gauge = sys / 'bus/i2c/devices/7-0055'
        gauge.mkdir(parents=True)
        (gauge / 'raw_device_type').write_text('42495\n')
        (gauge / 'battery_snapshot').write_text(
            'gauge_device_type=42495\ntemperature_millidegrees_celsius=27000\n'
            'temperature_error=0\nvoltage_error=0\ncurrent_error=0\n'
            'capacity_error=0\ncapacity_percent=72\n')
        etc = base / 'etc/lynx'
        etc.mkdir(parents=True)
        (etc / 'session-token').write_text('fixture-token\n')
        (run / 'host-confirmed').write_text('fixture-token\n')
        pack = base / 'pack'
        pack.mkdir()
        with tarfile.open(ARCHIVE, 'r:gz') as tar:
            for member in tar:
                if not member.isfile() or member.name.startswith('/') or '..' in Path(member.name).parts:
                    raise ValueError('Unsafe input pack')
                path = pack / member.name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(tar.extractfile(member).read())
        (pack / 'review/cpu-temperature-guard.sh').write_text(
            'lynx_cpu_temperature_guard() { echo CPU_TEMPERATURE_GUARD_OK; }\n')
        worker = '#!/bin/sh\ncase "${1:-}" in --once) exit 0;; esac\nwhile :; do sleep 100; done\n'
        for name in ('thermal-watch.sh', 'battery-watch.sh'):
            (pack / 'scripts' / name).write_text(worker)
        (pack / 'scripts/wfi-fallback.sh').write_text('#!/bin/sh\n[ "$1" = --apply ]\n')
        (pack / 'scripts/thermal-cooling-watch.sh').write_text(
            f'#!/bin/sh\nmkdir {run}/thermal-cooling-watch\n'
            f'echo $$ > {run}/thermal-cooling-watch/pid\n'
            f'echo ready > {run}/thermal-cooling-watch/ready\n'
            'while :; do sleep 100; done\n')
        (pack / 'scripts/lynx-health-supervisor.sh').write_text(
            f'#!/bin/sh\n[ "$1" = --once ] && exit 0\n'
            f'mkdir {run}/health-supervisor\n'
            f'echo $$ > {run}/health-supervisor/pid\n'
            'while :; do sleep 100; done\n')
        preflight = base / 'preflight.sh'
        preflight.write_text('#!/bin/sh\necho LYNX_HEALTH_PREFLIGHT_PASS\n')
        wrapper = base / 'busybox-mock.sh'
        wrapper.write_text(
            '#!/bin/sh\n'
            'case "$1" in\n'
            'insmod) name=${2##*/}; name=${name%.ko}; name=$(echo "$name" | tr - _); '
            f'mkdir {sys}/module/$name; exit $?;;\n'
            f'rmmod) rmdir {sys}/module/$2; exit $?;;\n'
            'poweroff) echo MOCK_POWEROFF >&2; exit 0;;\n'
            'nohup) shift; exec /usr/bin/nohup "$@";;\n'
            '*) exec /usr/bin/busybox "$@";;\n'
            'esac\n')
        wrapper.chmod(0o700)
        source = SOURCE.read_text()
        replacements = {
            'BB=/bin/busybox': 'BB=' + str(wrapper),
            'RUN=/run/lynx': 'RUN=' + str(run),
            'GAUGE=/sys/bus/i2c/devices/7-0055': 'GAUGE=' + str(gauge),
            '/usr/libexec/lynx/autonomous-health-preflight.sh': str(preflight),
            '/etc/lynx/session-token': str(etc / 'session-token'),
            '/dev/kmsg': str(base / 'kmsg'),
            '/sys/module/': str(sys / 'module') + '/',
            '/sys/class/thermal/': str(sys / 'class/thermal') + '/',
        }
        for old, new in replacements.items():
            if old not in source:
                raise ValueError('Fixture substitution point missing: ' + old)
            source = source.replace(old, new)
        script = base / 'start.sh'
        script.write_text(source)
        (run / 'host-confirmed').unlink()
        refused = subprocess.run(['sh', str(script), '--run', str(pack)],
                                 capture_output=True, text=True, timeout=5)
        if (refused.returncode == 0 or 'pinned host has not confirmed' not in refused.stdout
                or (run / 'health-bootstrap').exists() or list((sys / 'module').iterdir())):
            raise AssertionError('Unconfirmed boot was not refused before module insertion')
        (run / 'host-confirmed').write_text('fixture-token\n')
        result = None
        try:
            result = subprocess.run(['sh', str(script), '--run', str(pack)],
                                    capture_output=True, text=True, timeout=15)
            if result.returncode or 'READY_ON_PHONE_MONITORING_ACTIVE' not in result.stdout:
                raise AssertionError(f'Fixture startup failed: {result.returncode} {result.stdout} {result.stderr}')
            for name in ('thermal-watch.pid', 'battery-watch.pid',
                         'thermal-cooling-watch/pid', 'health-supervisor/pid'):
                if not (run / name).is_file():
                    raise AssertionError('Missing fake watcher PID: ' + name)
            if not (run / 'health-bootstrap/ready').is_file():
                raise AssertionError('Startup did not complete')
            stages = re.findall(r'LYNX_HEALTH_BOOT INSMOD_BEGIN (\w+)', result.stdout)
            expected = ['nvmem_mtk_devinfo', 'soc_temp_lvts', 'oplus_omrg',
                        'mediatek_cpufreq_hw', 'lynx_gauge_sample', 'lynx_battery_monitor']
            if stages != expected:
                raise AssertionError(f'Unexpected module order: {stages}')
        finally:
            for name in ('thermal-watch.pid', 'battery-watch.pid',
                         'thermal-cooling-watch/pid', 'health-supervisor/pid',
                         'health-bootstrap/timer.pid'):
                path = run / name
                if path.exists():
                    try:
                        os.kill(int(path.read_text().strip()), signal.SIGTERM)
                    except (ValueError, ProcessLookupError):
                        pass
        report = {'passed': True, 'host_gate_refused_before_module_insertion': True,
                  'module_order': stages, 'source_sha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
                  'fake_poweroff_invoked': 'MOCK_POWEROFF' in result.stderr,
                  'phone_contacted': False, 'flash_performed': False,
                  'limits': 'Synthetic filesystem and stubbed modules/watchers only; no stock-kernel or handset startup validation.'}
        if report['fake_poweroff_invoked']:
            raise AssertionError('Fixture unexpectedly requested power-off')
    out = PORT / 'artifacts' / ('autonomous-health-start-check-' + str(time.time_ns()))
    out.mkdir(mode=0o700)
    (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'passed': True, 'result': str(out / 'result.json')}))


if __name__ == '__main__':
    main()
