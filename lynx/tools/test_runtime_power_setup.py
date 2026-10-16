"""Run the real setup shell against a private synthetic filesystem.

Only already-running verification/adoption paths are exercised. Fresh driver
setup remains covered by the separate hardware trials, not simulated here.
"""
import hashlib
import json
import os
import re
import subprocess
import time
from pathlib import Path

from configure_runtime_power import ROOT, SOURCES, build_payload


def main():
    os.umask(0o077)
    out = ROOT / 'linux-port/artifacts' / ('runtime-power-setup-check-' + str(time.time_ns()))
    out.mkdir()
    original_payload = build_payload('apply').decode()
    for name, digest in SOURCES.items():
        marker = 'LYNX_SOURCE_' + digest
        embedded = original_payload.split("<<'" + marker + "'\n", 1)[1].split('\n' + marker + '\n', 1)[0] + '\n'
        if hashlib.sha256(embedded.encode()).hexdigest() != digest:
            raise ValueError('Embedded source changed bytes: ' + name)
    results = []
    cases = ['verified-check', 'verified-apply-existing', 'source-mismatch', 'stale-battery',
             'invalid-battery', 'missing-wfi', 'partial-wfi-restore', 'wrong-process', 'dead-process',
             'missing-cooling-ready', 'missing-cpu']
    for case in cases:
        folder = out / case
        folder.mkdir()
        run = folder / 'run/lynx'
        proc = folder / 'proc'
        sys = folder / 'sys'

        def write(relative, data):
            path = folder / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data if isinstance(data, bytes) else data.encode())

        write('proc/uptime', '100.00 800.00\n')
        write('proc/sys/kernel/random/boot_id', 'synthetic-boot-id\n')
        write('run/lynx/battery-last', 'sample_uptime_seconds=99.00\ntemperature_error=0\nvoltage_error=0\ncurrent_error=0\ncapacity_error=0\n')
        # Three distinct live fixture child PIDs; kill -0 never sends a signal.
        children = [subprocess.Popen(['sleep', '30']) for _ in range(3)]
        try:
            for child, name, pidfile in zip(children,
                    ['thermal-watch.sh', 'battery-watch.sh', 'thermal-cooling-watch.sh'],
                    ['thermal-watch.pid', 'battery-watch.pid', 'thermal-cooling-watch/pid']):
                write('run/lynx/' + pidfile, str(child.pid) + '\n')
                write('proc/' + str(child.pid) + '/cmdline', b'sh\0' + str(run / name).encode() + b'\0')
            write('run/lynx/thermal-cooling-watch/ready', 'ready\n')
            write('run/lynx/thermal-cooling-watch.log', 'THERMAL_COOLING_SAMPLE temperature=25000 desired=0\n')
            originals = []
            for index in range(8):
                prefix = f'sys/devices/system/cpu/cpu{index}/cpuidle/'
                write(prefix + 'state0/name', 'WFI\n')
                write(prefix + 'state0/disable', '0\n')
                write(prefix + 'state1/name', 'deep\n')
                write(prefix + 'state1/disable', '1\n')
                originals.append(str(folder / prefix / 'state1/disable') + ' 0\n')
            write('run/lynx/wfi-fallback/original-flags', ''.join(originals))
            for name in SOURCES:
                write('run/lynx/' + name, (ROOT / 'linux-port' / name).read_bytes())
            write('usr/sbin/iw', '#!/bin/sh\necho "Power save: on"\n')
            (folder / 'usr/sbin/iw').chmod(0o700)
            if case == 'source-mismatch':
                write('run/lynx/wfi-fallback.sh', '# changed\n')
            elif case == 'stale-battery':
                path = run / 'battery-last'
                path.write_text(path.read_text().replace('99.00', '1.00'))
            elif case == 'invalid-battery':
                path = run / 'battery-last'
                path.write_text(path.read_text().replace('temperature_error=0', 'temperature_error=-5'))
            elif case == 'missing-wfi':
                (run / 'wfi-fallback/original-flags').unlink()
                (run / 'wfi-fallback').rmdir()
            elif case == 'partial-wfi-restore':
                write('sys/devices/system/cpu/cpu3/cpuidle/state1/disable', '0\n')
            elif case == 'wrong-process':
                write('proc/' + str(children[2].pid) + '/cmdline', b'unrelated\0')
            elif case == 'dead-process':
                children[2].terminate()
                children[2].wait()
            elif case == 'missing-cooling-ready':
                (run / 'thermal-cooling-watch/ready').unlink()
            elif case == 'missing-cpu':
                import shutil
                shutil.rmtree(sys / 'devices/system/cpu/cpu7')
            mode = 'apply' if case == 'verified-apply-existing' else 'check'
            payload = build_payload(mode)
            mappings = {'/run/lynx': str(run), '/proc/': str(proc) + '/',
                        '/sys/': str(sys) + '/', '/usr/sbin/iw': str(folder / 'usr/sbin/iw')}
            pattern = '|'.join(re.escape(key) for key in mappings)
            payload = re.sub(pattern, lambda match: mappings[match[0]], payload.decode()).encode()
            (folder / 'payload.sh').write_bytes(payload)
            protected = {path: path.read_bytes() for path in folder.rglob('*')
                         if path.is_file() and ('/sys/' in str(path) or path.name == 'original-flags')}
            result = subprocess.run(['sh', str(folder / 'payload.sh')], capture_output=True, timeout=5)
            (folder / 'stdout').write_bytes(result.stdout)
            (folder / 'stderr').write_bytes(result.stderr)
            expected_success = case.startswith('verified-')
            unchanged = all(path.read_bytes() == data for path, data in protected.items())
            passed = (result.returncode == 0) == expected_success and unchanged
            results.append({'case': case, 'exit_code': result.returncode, 'protected_state_unchanged': unchanged,
                            'passed': passed})
        finally:
            for child in children:
                if child.poll() is None:
                    child.terminate()
                child.wait()
    report = {'passed': all(result['passed'] for result in results), 'cases': results,
              'embedded_source_hashes_verified': True,
              'setup_source_sha256': hashlib.sha256((ROOT / 'tools/configure_runtime_power.py').read_bytes()).hexdigest(),
              'hardware_access': False, 'fresh_boot_installation_tested': False}
    (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'passed': report['passed'], 'cases': len(results), 'result': str(out / 'result.json')}))
    if not report['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
