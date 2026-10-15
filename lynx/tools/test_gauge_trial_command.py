"""Run the real remote-command text against local fixtures, never hardware."""
import hashlib
import json
import os
import subprocess
import time
from pathlib import Path

from lynx_gauge_trial import COMMAND, MODULE, MODULE_SHA, ROOT, validate_extra


def main():
    validate_extra(require_command_test=False)
    out = ROOT / 'linux-port/artifacts' / ('gauge-command-check-' + str(time.time_ns()))
    out.mkdir(mode=0o700)
    cases = []
    for name in ['good', 'already-bound', 'bad-module', 'hot', 'dead-timer', 'read-failed']:
        folder = out / name
        folder.mkdir()
        client = folder / 'client'
        (client / 'of_node').mkdir(parents=True)
        (client / 'name').write_text('bq27541-battery\n')
        (client / 'of_node/qcom,batt_bq28z610').write_bytes(b'')
        if name != 'read-failed':
            (client / 'raw_temperature_word').write_text('2981\n')
        if name == 'already-bound':
            (client / 'driver').symlink_to(folder / 'nonexistent-driver')
        ram = folder / 'ram'
        ram.mkdir()
        (ram / 'gauge-sample.ko').write_bytes(MODULE.read_bytes() if name != 'bad-module' else b'bad')
        (ram / 'thermal-stop.pid').write_text(str(os.getpid() if name != 'dead-timer' else 99999999) + '\n')
        (ram / 'thermal-cpu-trial').mkdir()
        (ram / 'thermal-cpu-trial/cpu-temperature-guard.sh').write_text(
            'lynx_cpu_temperature_guard() { return ' + ('1' if name == 'hot' else '0') + '; }\n')
        shim = folder / 'busybox-fixture'
        shim.write_text('''#!/bin/sh
case "$1" in
insmod|rmmod) printf '%s\n' "$*" >> "$GAUGE_FIXTURE_CALLS"; exit 0 ;;
*) exec /usr/bin/"$@" ;;
esac
''')
        shim.chmod(0o700)
        command = COMMAND.replace('/bin/busybox', str(shim)).replace('/sys/bus/i2c/devices/7-0055', str(client)).replace('/sys/module/lynx_gauge_sample', str(folder / 'module-absent')).replace('/run/lynx', str(ram))
        (folder / 'command.sh').write_text(command)
        calls = folder / 'calls.log'
        p = subprocess.run(['sh', '-c', command], capture_output=True, timeout=5,
                           env=dict(os.environ, GAUGE_FIXTURE_CALLS=str(calls)))
        (folder / 'stdout').write_bytes(p.stdout)
        (folder / 'stderr').write_bytes(p.stderr)
        invoked = calls.read_text().splitlines() if calls.exists() else []
        if name == 'good':
            passed = (p.returncode == 0 and len(invoked) == 2
                      and invoked[0].startswith('insmod ') and invoked[1] == 'rmmod lynx_gauge_sample'
                      and b'\n2981\n' in p.stdout and b'GAUGE_UNLOADED=0' in p.stdout)
        elif name == 'read-failed':
            passed = p.returncode != 0 and len(invoked) == 1 and invoked[0].startswith('insmod ')
        else:
            passed = p.returncode != 0 and not invoked
        cases.append({'case': name, 'exit_code': p.returncode, 'mock_kernel_operations': invoked, 'passed': passed})
    result = {'passed': all(row['passed'] for row in cases), 'cases': cases,
              'command_sha256': hashlib.sha256(COMMAND.encode()).hexdigest(),
              'module_sha256': MODULE_SHA, 'phone_contacted': False,
              'actual_kernel_operations_performed': False}
    (out / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'result': str(out / 'result.json'), 'passed': result['passed'],
                      'cases': [{k: v for k, v in row.items() if k != 'mock_kernel_operations'} for row in cases]}, indent=2))
    if not result['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
