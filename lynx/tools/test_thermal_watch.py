"""Run real watcher text on local temperature fixtures; power-off is mocked."""
import hashlib
import json
import os
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    source = (ROOT / 'linux-port/thermal-watch.sh').read_bytes()
    out = ROOT / 'linux-port/artifacts' / ('thermal-watch-check-' + str(time.time_ns()))
    out.mkdir(mode=0o700)
    cases = [('normal', '35000', True, False), ('below-cutoff', '59999', True, False),
             ('at-cutoff', '60000', True, True), ('above-cutoff', '65000', True, True),
             ('not-ready', '65000', False, False), ('invalid', 'bad', True, False),
             ('zero', '0', True, False), ('negative', '-1', True, False),
             ('missing', None, True, False)]
    results = []
    for name, value, ready, stop in cases:
        folder = out / name
        zone = folder / 'thermal/thermal_zone0'
        zone.mkdir(parents=True)
        (zone / 'type').write_text('soc_max\n')
        if value is not None:
            (zone / 'temp').write_text(value + '\n')
        if ready:
            (folder / 'ready').touch()
        shim = folder / 'busybox-fixture'
        shim.write_text('#!/bin/sh\n[ "$1" = poweroff ] && { echo requested >> "$WATCH_STOP_LOG"; exit 0; }\nexit 99\n')
        shim.chmod(0o700)
        text = source.decode().replace('BB=/bin/busybox', 'BB=' + str(shim)).replace('THERMAL_ROOT=/sys/class/thermal', 'THERMAL_ROOT=' + str(folder / 'thermal')).replace('READY=/run/lynx/thermal-watch.ready', 'READY=' + str(folder / 'ready'))
        script = folder / 'watch.sh'
        script.write_text(text)
        p = subprocess.run(['sh', str(script), '--once'], capture_output=True, timeout=3,
                           env=dict(os.environ, WATCH_STOP_LOG=str(folder / 'stop.log')))
        (folder / 'stdout').write_bytes(p.stdout)
        (folder / 'stderr').write_bytes(p.stderr)
        requested = (folder / 'stop.log').exists()
        results.append({'case': name, 'passed': requested == stop and p.returncode == (2 if stop else 0),
                        'mock_shutdown_requested': requested, 'exit_code': p.returncode})
    report = {'passed': all(r['passed'] for r in results), 'cases': results,
              'source_sha256': hashlib.sha256(source).hexdigest(),
              'phone_contacted': False, 'actual_shutdown_performed': False,
              'limits': 'Real shell logic with mocked power-off; does not prove hardware thermal accuracy or physical shutdown.'}
    (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'result': str(out / 'result.json'), **report}, indent=2))
    if not report['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
