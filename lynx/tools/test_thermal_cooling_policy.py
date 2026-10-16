"""Exercise actual shell decision logic without touching any hardware path."""
import hashlib
import json
import os
import shlex
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / 'linux-port/thermal-cooling-watch.sh'


def main():
    os.umask(0o077)
    output = ROOT / 'linux-port/artifacts' / ('thermal-cooling-policy-check-' + str(time.time_ns()))
    output.mkdir()
    cases = []
    for previous in (0, 1):
        for temperature, expected in [('0', previous), ('-1', previous), ('unavailable', previous),
                                      ('125001', previous), ('39999', 0), ('40000', 0),
                                      ('40001', previous), ('44999', previous),
                                      ('45000', 1), ('45001', 1), ('125000', 1)]:
            cases.append((['--decide', str(previous), temperature], str(expected)))
    # Transition hysteresis, external stronger limits, and ownership loss.
    cases += [(['--action', '1', '0', '0', '0'], 'limit'),
              (['--action', '0', '0', '0', '0'], 'hold'),
              (['--action', '1', '1', '0', '0'], 'hold'),
              (['--action', '1', '2', '0', '0'], 'hold'),
              (['--action', '0', '1', '0', '0'], 'hold'),
              (['--action', '1', '1', '1', '0'], 'hold'),
              (['--action', '0', '1', '1', '0'], 'restore'),
              (['--action', '0', '2', '1', '0'], 'cede'),
              (['--action', '1', '0', '1', '0'], 'cede'),
              (['--action', '1', '0', '0', '1'], 'hold'),
              (['--action', '0', 'bad', '1', '0'], 'unavailable')]
    records = []
    for index, (arguments, expected) in enumerate(cases):
        result = subprocess.run(['sh', str(SOURCE), *arguments], capture_output=True, timeout=3)
        (output / (str(index) + '.stdout')).write_bytes(result.stdout)
        (output / (str(index) + '.stderr')).write_bytes(result.stderr)
        records.append({'arguments': arguments, 'expected': expected, 'exit_code': result.returncode,
                        'passed': result.returncode == 0 and result.stdout.decode().strip() == expected})
    passed = all(record['passed'] for record in records)
    digest = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    hardware_script = ['#!/bin/sh', 'set -eu',
                       "printf '%s\\n' '" + digest + "  /run/lynx/thermal-cooling-watch.sh' | sha256sum -c -"]
    for arguments, expected in cases:
        command = 'sh /run/lynx/thermal-cooling-watch.sh ' + ' '.join(map(shlex.quote, arguments))
        hardware_script += ['actual=$(' + command + ')', '[ "$actual" = ' + shlex.quote(expected) + ' ]']
    hardware_script.append('echo THERMAL_COOLING_DECISION_CASES_PASSED_33')
    (output / 'hardware-decisions.sh').write_text('\n'.join(hardware_script) + '\n')
    report = {'passed': passed, 'source_sha256': digest,
              'cases': records, 'hardware_access': False,
              'scope': 'Actual shell hysteresis and ownership decisions; daemon loop and sysfs I/O not simulated.'}
    (output / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'passed': passed, 'cases': len(cases), 'result': str(output / 'result.json')}))
    if not passed:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
