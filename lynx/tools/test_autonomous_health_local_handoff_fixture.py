"""Exercise the V25 local health handoff with a stubbed child, offline."""
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
SOURCE = PORT / 'autonomous-health-local-handoff.sh'
ARCHIVE = PORT / 'artifacts/autonomous-health-inputs/inputs.tar.gz'


def scenario(parent, label, *, valid_hash=True, ready=True):
    base = parent / label
    base.mkdir()
    run = base / 'run/lynx'
    etc = base / 'etc/lynx'
    share = base / 'usr/share/lynx'
    libexec = base / 'usr/libexec/lynx'
    for path in (run, etc, share, libexec):
        path.mkdir(parents=True)
    (etc / 'session-token').write_text('fixture-token\n')
    (run / 'bootstrap-result').write_text('0\n')
    if ready:
        (run / 'local-boot-ready').write_text('fixture-token\n')
    archive = share / 'health-inputs.tar.gz'
    shutil.copyfile(ARCHIVE, archive)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    (share / 'health-inputs.sha256').write_text((digest if valid_hash else '0' * 64) + '\n')
    stub = libexec / 'autonomous-health-start.sh'
    stub.write_text(
        '#!/bin/sh\n'
        '[ "$1" = --run-local ] || exit 9\n'
        f'printf "#!/bin/sh\\nexit 0\\n" > {run}/lynx-health-supervisor.sh\n'
        'echo LOCAL_HEALTH_START_FIXTURE_PASS\n')
    source = SOURCE.read_text()
    for old, new in (
        ('/usr/share/lynx', str(share)),
        ('/run/lynx', str(run)),
        ('/etc/lynx', str(etc)),
        ('/usr/libexec/lynx', str(libexec)),
    ):
        if old not in source:
            raise ValueError('Missing local handoff substitution: ' + old)
        source = source.replace(old, new)
    handoff = base / 'handoff.sh'
    handoff.write_text(source)
    runner = base / 'runner.sh'
    runner.write_text(
        '#!/bin/sh\nBB=/usr/bin/busybox\nlog() { echo "LOG $*"; }\n'
        f'. {handoff}\nlynx_autonomous_health_local_handoff\n')
    result = subprocess.run(['sh', str(runner)], capture_output=True,
                            text=True, timeout=10)
    extracted = (run / 'health-inputs/manifest.json').exists()
    if valid_hash and ready:
        if result.returncode or 'LOCAL_HEALTH_BOOT_READY' not in result.stdout or not extracted:
            raise AssertionError(f'{label}: local handoff failed: {result.returncode} {result.stdout} {result.stderr}')
    elif result.returncode == 0 or extracted:
        raise AssertionError(f'{label}: invalid local gate reached archive extraction')
    return {'name': label, 'exit_code': result.returncode, 'extracted': extracted}


def main():
    os.umask(0o077)
    with tempfile.TemporaryDirectory(prefix='lynx-health-local-', dir=PORT / 'artifacts') as temp:
        root = Path(temp)
        checks = [scenario(root, 'success'),
                  scenario(root, 'bad-hash', valid_hash=False),
                  scenario(root, 'missing-ready', ready=False)]
    report = {'passed': True, 'checks': checks,
              'source_sha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
              'phone_contacted': False, 'flash_performed': False,
              'limits': 'Stub child and host filesystem only; V25 has not booted on Lynx.'}
    out = PORT / 'artifacts' / ('autonomous-health-local-check-' + str(time.time_ns()))
    out.mkdir(mode=0o700)
    (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'passed': True, 'result': str(out / 'result.json')}))


if __name__ == '__main__':
    main()
