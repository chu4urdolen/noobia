"""Run a bounded, logged command in the verified rootfs on its original boot."""
import json
import shlex
import subprocess
import sys
import uuid
from pathlib import Path

from alpine_rootfs import ROOT, ARCHIVE_SHA256
from fetch_alpine_rootfs import VERSION
from lynx_session_ssh import resolve


def main():
    arguments = sys.argv[1:]
    if arguments[:1] == ['--']:
        arguments = arguments[1:]
    if not arguments:
        print('Usage: tools/lynx-alpine COMMAND [ARG ...] (logged, maximum 60 seconds)')
        return
    _, _, session = resolve()
    candidates = []
    for path in (ROOT / 'logs').glob('alpine-rootfs-trial-*/result.json'):
        try:
            report = json.loads(path.read_text())
            if (report.get('native_rootfs_verified') and report.get('original_runtime_verified')
                    and report.get('rootfs_left_in_ram') and Path(report['session']) == session.resolve()
                    and report['rootfs_inventory']['archive_sha256'] == ARCHIVE_SHA256):
                candidates.append((report['started_ns'], report))
        except (KeyError, ValueError, OSError):
            continue
    if not candidates:
        raise SystemExit('No verified RAM rootfs for the current continuous session.')
    _, report = max(candidates, key=lambda item: item[0])
    boot_id = str(uuid.UUID(report['boot_id']))
    destination = '/run/lynx/alpine-' + VERSION
    if report['destination'] != destination:
        raise ValueError('Unexpected rootfs destination')
    command = ('set -eu; test "$(cat /proc/sys/kernel/random/boot_id)" = ' + boot_id
               + '; test "$(cat ' + destination + '/etc/alpine-release)" = ' + VERSION
               + '; /bin/busybox chroot ' + destination + ' ' + shlex.join(arguments))
    result = subprocess.run([sys.executable, str(ROOT / 'tools/lynx_live_command.py'),
                             '--session', str(session), '--name', 'alpine-cli', '--timeout', '60',
                             '--command', command], capture_output=True, timeout=125)
    try:
        metadata = json.loads(result.stdout)
        capture = Path(metadata['capture'])
    except (ValueError, KeyError):
        sys.stdout.buffer.write(result.stdout); sys.stderr.buffer.write(result.stderr)
        raise SystemExit(result.returncode or 1)
    if not metadata.get('native_identity_verified'):
        sys.stderr.buffer.write(result.stderr)
        raise SystemExit('Fresh native identity proof failed; no Alpine command executed.')
    if capture.exists():
        sys.stdout.buffer.write(capture.read_bytes())
        sys.stderr.buffer.write(capture.with_suffix('.stderr').read_bytes())
    else:
        sys.stderr.buffer.write(result.stderr)
    code = metadata.get('command_exit_code')
    raise SystemExit(code if isinstance(code, int) else 1)


if __name__ == '__main__':
    main()
