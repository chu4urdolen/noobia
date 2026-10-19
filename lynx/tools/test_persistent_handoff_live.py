"""Exercise the V29 handoff pre-exec path on Lynx without replacing PID 1."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from lynx_wifi_v19_contact import PROOF, proof_valid, ssh_command


ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / 'linux-port/persistent-openrc-handoff.sh'
BUILD = ROOT / 'linux-port/artifacts/persistent-openrc-v29-offline/build-result.json'
IP = '192.168.100.4'
V19_SHA = '5ce2dbf8a7c132fa7e31f6be70aa76f83afe8c293e2cd5f02251a532486fd851'
GUARD_SHA = '3b669e0e130474a4c6b4458b54d0a6f1cd372d145c1c0da372b13a1edeb31fb5'


def main():
    os.umask(0o077)
    source = SCRIPT.read_text()
    build = json.loads(BUILD.read_text())
    if hashlib.sha256(source.encode()).hexdigest() != build['script_sha256']['etc/lynx/persistent-openrc-handoff.sh']:
        raise ValueError('Source differs from frozen V29 candidate')
    replacements = {
        '/etc/lynx/openrc-handoff-guard.sh': '/run/lynx/openrc-handoff-guard.sh',
        'persistent_root=/run/lynx/persistent-alpine\n':
            'persistent_root=/run/lynx/persistent-alpine-preexec-fixture\n',
        '    exec $BB chroot "$persistent_root" /sbin/openrc-init\n':
            '''    for persistent_undo in run dev sys proc; do
        $BB umount "$persistent_root/$persistent_undo" || return 1
    done
    $BB umount "$persistent_root" || return 1
    $BB rmdir "$persistent_root" || return 1
    echo PERSISTENT_OPENRC_PREEXEC_FIXTURE_PASSED
    return 0
''',
    }
    fixture = source
    for old, new in replacements.items():
        if fixture.count(old) != 1:
            raise ValueError('Handoff substitution site differs: ' + old)
        fixture = fixture.replace(old, new)
    fixture = '''BB=/bin/busybox
log() { echo "LYNX_FIXTURE $*"; }
export LYNX_OPENRC_ARMING=1
''' + fixture + '\nlynx_persistent_openrc_handoff\n'
    out = ROOT / 'logs' / ('persistent-openrc-live-preexec-' + str(time.time_ns()))
    out.mkdir(mode=0o700)
    (out / 'fixture.sh').write_text(fixture)
    report = {'state': 'starting', 'created_ns': time.time_ns(),
              'source_sha256': hashlib.sha256(source.encode()).hexdigest(),
              'fixture_sha256': hashlib.sha256(fixture.encode()).hexdigest(),
              'fixture_changes': list(replacements), 'phone_ip': IP,
              'boot_image_changed': False, 'pid1_replaced': False,
              'phone_partition_writes': 'ext4 journal metadata from temporary rw mount only'}

    def save():
        tmp = out / 'result.tmp'
        tmp.write_text(json.dumps(report, indent=2) + '\n')
        tmp.replace(out / 'result.json')

    save()
    try:
        identity = subprocess.run(ssh_command(IP, PROOF), capture_output=True, timeout=15)
        if not proof_valid(identity.stdout.decode(errors='replace'), identity.returncode):
            raise ValueError('Pinned native SSH identity refused')
        preflight = '''set -eu
cat /proc/sys/kernel/random/boot_id
/bin/busybox sha256sum /dev/sdc39
cat /run/lynx/health-bootstrap/ready
/bin/busybox sha256sum /run/lynx/openrc-handoff-guard.sh
test ! -e /run/lynx/persistent-alpine-preexec-fixture
! grep -Eq '^/dev/sdc85 |^/dev/block/by-name/userdata ' /proc/mounts'''
        before = subprocess.run(ssh_command(IP, preflight), capture_output=True, timeout=30)
        (out / 'preflight.stdout').write_bytes(before.stdout)
        (out / 'preflight.stderr').write_bytes(before.stderr)
        lines = before.stdout.decode(errors='replace').splitlines()
        if (before.returncode or len(lines) != 4 or
                lines[1] != V19_SHA + '  /dev/sdc39' or lines[2] != 'ready' or
                lines[3] != GUARD_SHA + '  /run/lynx/openrc-handoff-guard.sh'):
            raise ValueError('Live preflight refused')
        boot_id = lines[0]
        report.update(state='preflight-passed', boot_id=boot_id)
        save()
        trial = subprocess.run(ssh_command(IP, 'sh -s'), input=fixture.encode(),
                               capture_output=True, timeout=30)
        (out / 'trial.stdout').write_bytes(trial.stdout)
        (out / 'trial.stderr').write_bytes(trial.stderr)
        if (trial.returncode or
                b'PERSISTENT_OPENRC_PREEXEC_FIXTURE_PASSED\n' not in trial.stdout):
            raise ValueError('Handoff pre-exec path failed; inspect mounts')
        postflight = '''set -eu
! grep -E 'persistent-alpine-preexec-fixture|^/dev/sdc85 |^/dev/block/by-name/userdata ' /proc/mounts
test ! -e /run/lynx/persistent-alpine-preexec-fixture
cat /proc/sys/kernel/random/boot_id
cat /run/lynx/health-bootstrap/ready'''
        after = subprocess.run(ssh_command(IP, postflight), capture_output=True, timeout=15)
        (out / 'postflight.stdout').write_bytes(after.stdout)
        (out / 'postflight.stderr').write_bytes(after.stderr)
        if after.returncode or after.stdout.decode(errors='replace').splitlines() != [boot_id, 'ready']:
            raise ValueError('Postflight mount or health state differs')
        report['state'] = 'live-preexec-path-passed'
    except Exception as error:
        report.update(state='failed-or-incomplete', error=str(error))
    report['finished_ns'] = time.time_ns()
    save()
    print(json.dumps({'state': report['state'], 'result': str(out / 'result.json')}))
    if report['state'] != 'live-preexec-path-passed':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
