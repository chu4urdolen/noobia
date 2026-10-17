"""Synthetic handoff test using the exact inert health archive and stub workers."""
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PORT = ROOT / 'linux-port'
SOURCE = PORT / 'autonomous-health-handoff.sh'
ARCHIVE = PORT / 'artifacts/autonomous-health-inputs/inputs.tar.gz'


def scenario(parent, label, *, valid_hash=True, confirmed=True):
    base = parent / label
    base.mkdir()
    run = base / 'run/lynx'
    etc = base / 'etc/lynx'
    share = base / 'usr/share/lynx'
    libexec = base / 'usr/libexec/lynx'
    for path in (run, etc, share, libexec):
        path.mkdir(parents=True)
    (etc / 'session-token').write_text('fixture-token\n')
    (run / 'host-confirmed').write_text(('fixture-token' if confirmed else 'wrong-token') + '\n')
    archive = share / 'health-inputs.tar.gz'
    shutil.copyfile(ARCHIVE, archive)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    (share / 'health-inputs.sha256').write_text((digest if valid_hash else '0' * 64) + '\n')
    stub = libexec / 'autonomous-health-start.sh'
    stub.write_text(
        '#!/bin/sh\n'
        f'echo "#!/bin/sh" > {run}/lynx-health-supervisor.sh\n'
        f'echo "exit 0" >> {run}/lynx-health-supervisor.sh\n'
        'echo HEALTH_START_FIXTURE_PASS\n')
    openrc = etc / 'openrc-handoff.sh'
    openrc.write_text('lynx_openrc_handoff() { echo OPENRC_FIXTURE_PASS; }\n')
    source = SOURCE.read_text()
    for old, new in (
        ('/usr/share/lynx', str(share)),
        ('/run/lynx', str(run)),
        ('/etc/lynx', str(etc)),
        ('/usr/libexec/lynx', str(libexec)),
    ):
        if old not in source:
            raise ValueError('Missing handoff fixture substitution: ' + old)
        source = source.replace(old, new)
    handoff = base / 'handoff.sh'
    handoff.write_text(source)
    runner = base / 'runner.sh'
    runner.write_text(
        '#!/bin/sh\nBB=/usr/bin/busybox\nlog() { echo "LOG $*"; }\n'
        f'. {handoff}\nlynx_autonomous_health_handoff\n')
    result = subprocess.run(['sh', str(runner)], capture_output=True,
                            text=True, timeout=10)
    if valid_hash and confirmed:
        if result.returncode or 'OPENRC_FIXTURE_PASS' not in result.stdout:
            raise AssertionError(f'{label}: expected success: {result.returncode} {result.stdout} {result.stderr}')
        if not (run / 'openrc-handoff-ready').is_file() or not (run / 'health-inputs/manifest.json').is_file():
            raise AssertionError(f'{label}: archive extraction or gate arming missing')
    else:
        if result.returncode == 0 or (run / 'openrc-handoff-ready').exists():
            raise AssertionError(f'{label}: failed gate armed OpenRC')
    return {'name': label, 'exit_code': result.returncode,
            'openrc_armed': (run / 'openrc-handoff-ready').exists()}


def main():
    os.umask(0o077)
    with tempfile.TemporaryDirectory(prefix='lynx-health-handoff-', dir=PORT / 'artifacts') as temp:
        root = Path(temp)
        checks = [scenario(root, 'success'),
                  scenario(root, 'bad-hash', valid_hash=False),
                  scenario(root, 'wrong-host', confirmed=False)]
    report = {'passed': True, 'checks': checks,
              'source_sha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
              'phone_contacted': False, 'flash_performed': False,
              'limits': 'Stub startup/OpenRC and host filesystem only; no stock-kernel or phone boot of V24.'}
    out = PORT / 'artifacts' / ('autonomous-health-handoff-check-' + str(time.time_ns()))
    out.mkdir(mode=0o700)
    (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'passed': True, 'result': str(out / 'result.json')}))


if __name__ == '__main__':
    main()
