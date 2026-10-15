"""Bounded, read-only stock Fastboot fetch probe; retain raw results."""
import hashlib
import json
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FASTBOOT = ROOT / 'tools/platform-tools/fastboot'
SERIAL = '89BYAY5L4T9HFUOV'


def main():
    out = ROOT / 'logs' / ('fastboot-readback-' + str(time.time_ns()))
    out.mkdir(mode=0o700)
    report = {'purpose': 'read-only retrieval capability; no flash, erase or authentication bypass',
              'started_ns': time.time_ns(), 'operations': [], 'fetch_verified': False}
    receipt = out / 'result.json'

    def save():
        temporary = receipt.with_suffix('.tmp')
        temporary.write_text(json.dumps(report, indent=2) + '\n')
        temporary.replace(receipt)

    save()
    preflight = subprocess.run(['python3', str(ROOT / 'tools/lynx_fastboot_preflight.py'), '--connect'],
                               capture_output=True, timeout=30)
    (out / 'preflight.raw').write_bytes(preflight.stdout + preflight.stderr)
    report['preflight_exit_code'] = preflight.returncode
    save()
    if preflight.returncode:
        print('Preflight failed; no readback attempted:', receipt)
        return
    destination = out / 'boot_a.img'
    for arguments in [['getvar', 'max-fetch-size'], ['fetch', 'boot_a', str(destination)]]:
        command = [str(FASTBOOT), '-s', SERIAL, *arguments]
        operation = {'command': command, 'started_ns': time.time_ns()}
        started = time.monotonic()
        report['operations'].append(operation)
        save()
        try:
            process = subprocess.run(command, capture_output=True, timeout=30)
            raw = process.stdout + process.stderr
            operation.update(state='returned', exit_code=process.returncode)
        except subprocess.TimeoutExpired as error:
            raw = (error.stdout or b'') + (error.stderr or b'')
            operation.update(state='timeout', exit_code=None)
        (out / ('operation-' + str(len(report['operations'])) + '.raw')).write_bytes(raw)
        operation.update(elapsed_seconds=time.monotonic() - started, finished_ns=time.time_ns(),
                         output=raw.decode(errors='replace'))
        save()
        print(operation['output'], end='', flush=True)
        if operation['state'] == 'timeout':
            break
    if destination.exists():
        destination.chmod(0o600)
        data = destination.read_bytes()
        report.update(readback_bytes=len(data), readback_sha256=hashlib.sha256(data).hexdigest())
        report['fetch_verified'] = (report['operations'][-1]['exit_code'] == 0
                                    and len(data) == 67108864
                                    and hashlib.sha256(data).hexdigest() ==
                                    'a67f03d7b826b834c23653b67eaa6efa971eb70ef8af19eee4d33fb5fc7fe995')
    report['finished_ns'] = time.time_ns()
    save()
    print('Readback verified:', report['fetch_verified'], 'Receipt:', receipt)


if __name__ == '__main__':
    main()
