"""Exercise V32's exact PID 1 retry tail with synthetic guard outcomes."""
import json
from pathlib import Path
import subprocess
import tempfile

from build_persistent_openrc_v32 import REPLACEMENT


def fixture(mode):
    with tempfile.TemporaryDirectory(prefix='lynx-v32-retry-') as directory:
        root = Path(directory)
        tail = REPLACEMENT.decode().split('openrc_attempt=1\n', 1)[1]
        tail = ('openrc_attempt=1\n' + tail).replace(
            '/run/lynx/boot.log', str(root / 'boot.log')).replace(
            '/run/lynx/persistent-alpine', str(root / 'persistent-alpine')).replace(
            '$BB sleep 5', ': # fixture omits delay')
        setup = '''#!/bin/sh
set -eu
BB=/usr/bin/busybox
count=0
log() { printf 'LYNX_WIFI uptime=1 %s\\n' "$*" >> "$1"; }
'''
        # Keep the production log() call signature while pinning its file.
        setup = setup.replace('log() { printf \'LYNX_WIFI uptime=1 %s\\n\' "$*" >> "$1"; }',
                              'log() { printf \'LYNX_WIFI uptime=1 %s\\n\' "$*" >> "' + str(root / 'boot.log') + '"; }')
        setup += '''lynx_persistent_openrc_wait_and_handoff() {
    count=$((count + 1))
    case "''' + mode + '''" in
        transient) [ "$count" -eq 1 ] || return 0 ;;
        persistent) ;;
        nonguard) log 'PERSISTENT_OPENRC_ROOT_ID_REFUSED'; return 1 ;;
        partial) mkdir "''' + str(root / 'persistent-alpine') + '''" ;;
    esac
    log 'PERSISTENT_OPENRC_SAFETY_GUARD_REFUSED'
    return 1
}
stop() { echo "ATTEMPTS=$count"; }
'''
        run = subprocess.run(['/usr/bin/busybox', 'sh'], input=(setup + tail).encode(),
                             capture_output=True, timeout=10)
        if run.returncode:
            raise ValueError(f'{mode}: shell failed: {run.stderr.decode()}')
        expected = {'transient': 2, 'persistent': 3, 'nonguard': 1, 'partial': 1}[mode]
        if f'ATTEMPTS={expected}\n'.encode() not in run.stdout:
            raise ValueError(f'{mode}: wrong retry count: {run.stdout!r}')
        log = (root / 'boot.log').read_text()
        return {'mode': mode, 'attempts': expected,
                'clean_retry_lines': log.count('PERSISTENT_OPENRC_GUARD_CLEAN_RETRY')}


def main():
    outcomes = [fixture(mode) for mode in ('transient', 'persistent', 'nonguard', 'partial')]
    assert [v['clean_retry_lines'] for v in outcomes] == [1, 2, 0, 0]
    print(json.dumps({'state': 'v32-retry-fixtures-passed', 'outcomes': outcomes}))


if __name__ == '__main__':
    main()
