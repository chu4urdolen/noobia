"""Restore the VM-verified Alpine development checkpoint into Lynx RAM.

Requires fresh pinned V19 SSH and the autonomous health stage on the same boot.
Only /run is changed; no phone partition is mounted or written.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import uuid

from lynx_wifi_v19_contact import PROOF, proof_valid, ssh_command

ROOT = Path(__file__).resolve().parent.parent
CHECKPOINT = ROOT / 'checkpoints/alpine-runtime-1792331453858559525'
VALIDATION = ROOT / 'linux-port/artifacts/alpine-checkpoint-restore-1792331497398834530/result.json'
DEST = '/run/lynx/alpine-3.24.2'
ARCHIVE_REMOTE = DEST + '.tar.gz'
HEALTH_TRACE = ('/bin/busybox tail -n 200 -f '
                '/run/lynx/health-supervisor/events.log '
                '/run/lynx/thermal-watch.log '
                '/run/lynx/battery-watch.log '
                '/run/lynx/thermal-cooling-watch.log')


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--contact-receipt', type=Path)
    parser.add_argument('--health-receipt', type=Path)
    parser.add_argument('--restore', action='store_true')
    args = parser.parse_args()
    checkpoint_receipt = CHECKPOINT / 'result.json'
    checkpoint = json.loads(checkpoint_receipt.read_text())
    archive = CHECKPOINT / 'rootfs.tar.gz'
    vm = json.loads(VALIDATION.read_text())
    if (checkpoint.get('state') != 'checkpoint-verified' or
            checkpoint.get('archive_sha256') != sha(archive) or
            checkpoint.get('archive_bytes') != archive.stat().st_size or
            checkpoint.get('restore_validation') != str(VALIDATION) or
            checkpoint.get('restore_validation_sha256') != sha(VALIDATION) or
            vm.get('state') != 'restoration-verified' or
            vm.get('checkpoint_sha256') != checkpoint['archive_sha256'] or
            not vm.get('checks', {}).get('python_git_make_run') or
            not vm.get('checks', {}).get('package_world_match')):
        raise ValueError('Checkpoint or stock-kernel VM validation differs')
    if not args.restore:
        print(json.dumps({'state': 'offline-ready', 'archive_sha256': sha(archive),
                          'phone_contacted': False, 'partition_writes': False}))
        return
    if args.contact_receipt is None or args.health_receipt is None:
        parser.error('--restore needs --contact-receipt and --health-receipt')
    contact = json.loads(args.contact_receipt.read_text())
    health = json.loads(args.health_receipt.read_text())
    valid_health = health.get('state') == 'phone-ram-health-stage-verified'
    valid_local_health = (
        health.get('state') == 'local-health-in-ram-verified' and
        health.get('usb_unplugged_confirmed') is True and
        health.get('partition_writes') is False and
        health.get('flash_performed') is False and
        any(op.get('name') == 'local-health-handoff' and op.get('exit_code') == 0
            for op in health.get('operations', [])) and
        any(op.get('name') == 'cancel-outer-timer' and op.get('exit_code') == 0
            for op in health.get('operations', [])))
    if (contact.get('state') != 'native-ssh-available' or
            not contact.get('native_ssh_verified') or
            contact.get('fallback_cancel_ack_exit_code') != 0 or
            not (valid_health or valid_local_health) or
            health.get('contact_receipt') != str(args.contact_receipt.resolve()) or
            health.get('phone_ip') != contact.get('phone_ip')):
        raise ValueError('Fresh pinned V19 and same-session health receipts required')
    ip = contact['phone_ip']
    os.umask(0o077)
    out = ROOT / 'logs' / ('alpine-checkpoint-live-restore-' + str(time.time_ns()))
    out.mkdir(mode=0o700)
    report = {'state': 'starting', 'created_ns': time.time_ns(),
              'contact_receipt': str(args.contact_receipt.resolve()),
              'health_receipt': str(args.health_receipt.resolve()),
              'archive_sha256': checkpoint['archive_sha256'],
              'destination': DEST, 'partition_writes': False,
              'flash_performed': False, 'operations': []}
    trace = None
    trace_stdout = None
    trace_stderr = None

    def save():
        temporary = out / 'result.tmp'
        temporary.write_text(json.dumps(report, indent=2) + '\n')
        temporary.replace(out / 'result.json')

    def run(name, command, *, input_path=None, timeout=25):
        operation = {'name': name, 'started_ns': time.time_ns()}
        report['operations'].append(operation)
        save()
        with (out / (name + '.stdout')).open('wb') as stdout, \
                (out / (name + '.stderr')).open('wb') as stderr:
            source = input_path.open('rb') if input_path else subprocess.DEVNULL
            try:
                child = subprocess.run(ssh_command(ip, command), stdin=source,
                                       stdout=stdout, stderr=stderr, timeout=timeout)
                operation['exit_code'] = child.returncode
            except subprocess.TimeoutExpired:
                operation.update(exit_code=None, timed_out=True)
            finally:
                if input_path:
                    source.close()
        raw = (out / (name + '.stdout')).read_bytes()
        operation.update(finished_ns=time.time_ns(), stdout_bytes=len(raw),
                         stdout_sha256=hashlib.sha256(raw).hexdigest())
        save()
        if operation['exit_code'] != 0:
            raise ValueError(name + ' failed; partial RAM files retained')
        return raw

    try:
        proof = run('identity', PROOF)
        if not proof_valid(proof.decode(errors='replace'), 0):
            raise ValueError('Pinned V19 identity differs')
        preflight = '''set -eu
boot=$(cat /proc/sys/kernel/random/boot_id)
[ -r /run/lynx/health-bootstrap/ready ]
[ "$(cat /run/lynx/health-bootstrap/ready)" = ready ]
[ -r /run/lynx/health-supervisor/pid ]
kill -0 "$(cat /run/lynx/health-supervisor/pid)"
for field in temperature_error voltage_error current_error capacity_error; do
    grep -Fx "$field=0" /run/lynx/battery-last >/dev/null
done
temperature=$(sed -n 's/^temperature_millidegrees_celsius=//p' /run/lynx/battery-last)
capacity=$(sed -n 's/^capacity_percent=//p' /run/lynx/battery-last)
[ "$temperature" -gt 0 ] && [ "$temperature" -lt 35000 ]
[ "$capacity" -ge 20 ]
supplies=0
for p in /sys/class/power_supply/*; do
    [ -r "$p/online" ] || continue
    [ "$(cat "$p/online")" = 0 ]
    supplies=$((supplies+1))
done
[ "$supplies" -ge 1 ]
available=$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo)
[ "$available" -ge 1048576 ]
awk '$2=="/run" && $3=="tmpfs" {ok=1} END {exit !ok}' /proc/mounts
[ ! -e ''' + DEST + ''' ]
[ ! -e ''' + ARCHIVE_REMOTE + ''' ]
echo "$boot"'''
        boot_raw = run('preflight', preflight)
        boot_id = str(uuid.UUID(boot_raw.decode().strip().splitlines()[-1]))
        report['boot_id'] = boot_id
        save()
        trace_stdout = (out / 'health-runtime-trace.stdout').open('wb')
        trace_stderr = (out / 'health-runtime-trace.stderr').open('wb')
        trace = subprocess.Popen(ssh_command(ip, HEALTH_TRACE),
                                 stdin=subprocess.DEVNULL,
                                 stdout=trace_stdout, stderr=trace_stderr)
        report['health_trace_started_ns'] = time.time_ns()
        save()
        guard = 'set -eu; [ "$(cat /proc/sys/kernel/random/boot_id)" = ' + boot_id + ' ]; '
        remount = guard + '''limit=$(df -Pk /run | awk 'END {print $2}');
case "$limit" in 131072) /bin/busybox mount -t tmpfs -o remount,size=256m tmpfs /run ;;
262144) : ;; *) exit 1 ;; esac;
[ "$(df -Pk /run | awk 'END {print $2}')" = 262144 ];
[ "$(df -Pk /run | awk 'END {print $4}')" -ge 180000 ];
echo RAM_LIMIT_READY'''
        if b'RAM_LIMIT_READY' not in run('ram-limit', remount):
            raise ValueError('RAM limit confirmation missing')
        upload = (guard + '[ ! -e ' + ARCHIVE_REMOTE + ' ]; cat > ' +
                  ARCHIVE_REMOTE + '.partial; echo "' + checkpoint['archive_sha256'] +
                  '  ' + ARCHIVE_REMOTE + '.partial" | /bin/busybox sha256sum -c -; '
                  'mv ' + ARCHIVE_REMOTE + '.partial ' + ARCHIVE_REMOTE)
        run('upload', upload, input_path=archive, timeout=120)
        extract = (guard + '[ ! -e ' + DEST + ' ]; mkdir ' + DEST + '; '
                   '/bin/busybox tar -xzf ' + ARCHIVE_REMOTE + ' -C ' + DEST + '; '
                   '[ "$(cat ' + DEST + '/etc/alpine-release)" = 3.24.2 ]; '
                   '/bin/busybox mkdir -p ' + DEST + '/dev; '
                   '[ -e ' + DEST + '/dev/null ] || /bin/busybox mknod -m 666 ' +
                   DEST + '/dev/null c 1 3; '
                   '[ -c ' + DEST + '/dev/null ]; '
                   '/bin/busybox chroot ' + DEST +
                   ' /bin/sh -c "python3 --version && git --version && make --version"; '
                   'rm ' + ARCHIVE_REMOTE + '; echo LYNX_ALPINE_CHECKPOINT_LIVE_READY')
        if b'LYNX_ALPINE_CHECKPOINT_LIVE_READY' not in run('extract-probe', extract, timeout=70):
            raise ValueError('Alpine live proof missing')
        final = guard + '''[ "$(cat /run/lynx/health-bootstrap/ready)" = ready ];
kill -0 "$(cat /run/lynx/health-supervisor/pid)";
[ -d ''' + DEST + ''' ]; echo HEALTH_AND_ALPINE_READY'''
        if b'HEALTH_AND_ALPINE_READY' not in run('final-health', final):
            raise ValueError('Health and Alpine final proof missing')
        stable = guard + '''[ "$(cat /run/lynx/health-bootstrap/ready)" = ready ];
kill -0 "$(cat /run/lynx/health-supervisor/pid)";
/bin/busybox sh /run/lynx/lynx-health-supervisor.sh --once;
[ -d ''' + DEST + ''' ]; echo STABLE_HEALTH_AND_ALPINE'''
        for check in range(3):
            time.sleep(10)
            if b'STABLE_HEALTH_AND_ALPINE' not in run(
                    'stability-' + str(check + 1), stable, timeout=15):
                raise ValueError('Alpine or health failed 30-second stability check')
        report['state'] = 'alpine-checkpoint-live-in-ram'
    except Exception as error:
        report.update(state='failed', error=str(error))
    if trace is not None and trace.poll() is None:
        trace.terminate()
        try:
            trace.wait(timeout=3)
        except subprocess.TimeoutExpired:
            trace.kill()
            trace.wait()
    if trace_stdout is not None:
        trace_stdout.close()
    if trace_stderr is not None:
        trace_stderr.close()
    trace_path = out / 'health-runtime-trace.stdout'
    if trace_path.exists():
        report['health_trace_bytes'] = trace_path.stat().st_size
        report['health_trace_sha256'] = sha(trace_path)
    report['finished_ns'] = time.time_ns()
    save()
    print(json.dumps({'state': report['state'], 'result': str(out / 'result.json')}))
    if report['state'] != 'alpine-checkpoint-live-in-ram':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
