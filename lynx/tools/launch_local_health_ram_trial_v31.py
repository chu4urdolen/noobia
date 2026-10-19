"""Test V31's guarded cooling startup on a fresh V19 boot, in RAM only."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from launch_autonomous_health_ram_trial import ARCHIVE, PREFLIGHT, validate_local
from lynx_wifi_v19_contact import PROOF, proof_valid, ssh_command

ROOT = Path(__file__).resolve().parent.parent
PORT = ROOT / 'linux-port'
START = PORT / 'autonomous-health-start-v31.sh'
OLD_START = PORT / 'autonomous-health-start.sh'
HANDOFF = PORT / 'autonomous-health-local-handoff.sh'
V28_BUILD = PORT / 'artifacts/local-health-v28-offline/build-result.json'
REMOTE_LIB = '/usr/libexec/lynx'
REMOTE_SHARE = '/usr/share/lynx'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def save(path, value):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, indent=2) + '\n')
    temp.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--prepare', action='store_true')
    modes.add_argument('--run', action='store_true')
    parser.add_argument('--contact-receipt', type=Path)
    parser.add_argument('--usb-unplugged-confirmed', action='store_true')
    args = parser.parse_args()
    local = validate_local()
    build = json.loads(V28_BUILD.read_text())
    handoff = HANDOFF.read_bytes()
    fixture_paths = [PORT / 'artifacts/autonomous-health-start-check-1792430456291629151/result.json',
                     PORT / 'artifacts/autonomous-health-start-check-1792430466420875201/result.json',
                     PORT / 'artifacts/autonomous-health-start-check-1792430435474100271/result.json']
    fixtures = [json.loads(path.read_text()) for path in fixture_paths]
    if (build.get('health_start_sha256') != sha(OLD_START.read_bytes()) or
            build.get('local_handoff_sha256') != sha(handoff) or
            build.get('image_sha256') !=
            'a22048376cec353af652c187da733eb198f1382efcf19924eebd5ba0b883d775'):
        raise ValueError('V28 health handoff provenance differs')
    if (len(fixtures) != 3 or
            {(f.get('mode'), f.get('cooling_behavior')) for f in fixtures} !=
            {('host', 'transient'), ('local', 'transient'), ('host', 'partial')} or
            any(not f.get('passed') or f.get('source_sha256') != sha(START.read_bytes())
                for f in fixtures)):
        raise ValueError('V31 startup fixture provenance differs')
    if subprocess.run(['sh', '-n'], input=handoff, capture_output=True).returncode:
        raise ValueError('Local handoff shell syntax failed')
    expected_hash = local['archive_sha256'] + '\n'
    if (PORT / 'artifacts/health-stage-v23-offline/build-result.json').exists() is False:
        raise ValueError('Reviewed health package missing')
    if args.prepare:
        print(json.dumps({'state': 'offline-ready-for-fresh-v19-local-health-v31-ram-trial',
                          'v28_image_sha256': build['image_sha256'],
                          'v31_start_sha256': sha(START.read_bytes()),
                          'handoff_sha256': sha(handoff), 'health_input_sha256': local['archive_sha256'],
                          'phone_contacted': False, 'flash_performed': False}))
        return
    if args.contact_receipt is None or not args.usb_unplugged_confirmed:
        parser.error('--run needs fresh --contact-receipt and --usb-unplugged-confirmed')
    contact_path = args.contact_receipt.resolve(strict=True)
    if not contact_path.is_relative_to(ROOT / 'logs'):
        raise ValueError('Contact receipt escaped Lynx logs')
    contact = json.loads(contact_path.read_text())
    if (contact.get('state') != 'native-ssh-available' or
            contact.get('native_ssh_verified') is not True or
            contact.get('fallback_cancel_ack_exit_code') != 0):
        raise ValueError('Fresh pinned V19 contact missing')
    ip = contact['phone_ip']
    os.umask(0o077)
    out = ROOT / 'logs' / ('local-health-v31-ram-trial-' + str(time.time_ns()))
    out.mkdir(mode=0o700)
    report = {'state': 'starting', 'started_ns': time.time_ns(),
              'contact_receipt': str(contact_path), 'phone_ip': ip,
              'v28_image_sha256': build['image_sha256'],
              'v31_start_sha256': sha(START.read_bytes()),
              'usb_unplugged_confirmed': True, 'partition_writes': False,
              'flash_performed': False, 'operations': []}
    receipt = out / 'result.json'
    save(receipt, report)

    def run(name, command, *, data=None, timeout=12):
        event = {'name': name, 'started_ns': time.time_ns(), 'command': command}
        report['operations'].append(event)
        save(receipt, report)
        stdout_path, stderr_path = out / (name + '.stdout'), out / (name + '.stderr')
        with stdout_path.open('wb') as stdout, stderr_path.open('wb') as stderr:
            try:
                proc = subprocess.run(ssh_command(ip, command), input=data,
                                      stdout=stdout, stderr=stderr, timeout=timeout)
                event['exit_code'] = proc.returncode
            except subprocess.TimeoutExpired:
                event.update(exit_code=None, timed_out=True)
        raw = stdout_path.read_bytes()
        event.update(finished_ns=time.time_ns(), stdout_bytes=len(raw), stdout_sha256=sha(raw))
        save(receipt, report)
        return raw, event['exit_code']

    protected = False
    timer_armed = False
    stream = None
    stream_stdout = None
    stream_stderr = None
    try:
        proof, rc = run('identity', PROOF)
        if not proof_valid(proof.decode(errors='replace'), rc):
            raise ValueError('Pinned V19 identity differs')
        precheck = '''set -e
[ -r /run/lynx/host-confirmed ]
[ "$(cat /run/lynx/bootstrap-result)" = 0 ]
for n in nvmem_mtk_devinfo soc_temp_lvts oplus_omrg mediatek_cpufreq_hw lynx_battery_monitor; do
    [ ! -d "/sys/module/$n" ]
done
[ ! -e /run/lynx/health-bootstrap ]
[ ! -e /run/lynx/local-boot-ready ]
now=$(cut -d. -f1 /proc/uptime)
start=$(cat /run/lynx/network-timing-start)
case "$now:$start" in *[!0-9:]*) exit 1;; esac
[ "$now" -ge "$start" ] && [ "$((now-start))" -lt 240 ]
supplies=0
for p in /sys/class/power_supply/*; do
    [ -r "$p/online" ] || continue
    [ "$(cat "$p/online")" = 0 ]
    supplies=$((supplies+1))
done
[ "$supplies" -ge 1 ]
echo FRESH_UNPLUGGED_LOCAL_HEALTH_READY'''
        raw, rc = run('fresh-precheck', precheck)
        if rc or b'FRESH_UNPLUGGED_LOCAL_HEALTH_READY' not in raw:
            raise ValueError('Fresh unplugged V19 precheck refused')
        _, rc = run('prepare-ram-directories',
                    'mkdir -p ' + REMOTE_LIB + ' ' + REMOTE_SHARE +
                    ' && test ! -e ' + REMOTE_SHARE + '/health-inputs.tar.gz')
        if rc:
            raise ValueError('RAM directories unavailable')
        sources = [(PREFLIGHT, REMOTE_LIB + '/' + PREFLIGHT.name),
                   (START, REMOTE_LIB + '/autonomous-health-start.sh'),
                   (HANDOFF, REMOTE_LIB + '/' + HANDOFF.name)]
        for path, destination in sources:
            _, rc = run('upload-' + path.stem,
                        'test ! -e ' + destination + ' && cat > ' + destination,
                        data=path.read_bytes())
            if rc:
                raise ValueError('RAM script upload failed: ' + path.name)
        for name, data in [('health-inputs.tar.gz', ARCHIVE.read_bytes()),
                           ('health-inputs.sha256', expected_hash.encode())]:
            destination = REMOTE_SHARE + '/' + name
            _, rc = run('upload-' + name,
                        'test ! -e ' + destination + ' && cat > ' + destination, data=data)
            if rc:
                raise ValueError('RAM health input upload failed: ' + name)
        checks = [(REMOTE_LIB + '/' + PREFLIGHT.name, sha(PREFLIGHT.read_bytes())),
                  (REMOTE_LIB + '/autonomous-health-start.sh', sha(START.read_bytes())),
                  (REMOTE_LIB + '/' + HANDOFF.name, sha(handoff)),
                  (REMOTE_SHARE + '/health-inputs.tar.gz', local['archive_sha256'])]
        command = 'set -e; ' + '; '.join(
            'echo "' + digest + '  ' + path + '" | /bin/busybox sha256sum -c -'
            for path, digest in checks)
        _, rc = run('verify-uploads', command)
        if rc:
            raise ValueError('RAM input hashes differ')
        command = ("set -e; token=$(cat /etc/lynx/session-token); "
                   "[ -n \"$token\" ]; printf '%s\\n' \"$token\" > /run/lynx/local-boot-ready; "
                   "( /bin/busybox sleep 300; /bin/busybox poweroff -f ) "
                   "> /run/lynx/local-health-ram-timer.log 2>&1 < /dev/null & "
                   "echo $! > /run/lynx/local-health-ram-timer.pid")
        _, rc = run('arm-local-marker-and-safety-timer', command)
        if rc:
            raise ValueError('Local marker or independent timer failed')
        timer_armed = True
        report['state'] = 'local-health-running-on-phone'
        save(receipt, report)
        stream_command = ('while [ ! -e /run/lynx/health-bootstrap-child.log ]; do '
                          '/bin/busybox sleep 1; done; '
                          'exec /bin/busybox tail -n 1000 -f '
                          '/run/lynx/health-bootstrap-child.log /run/lynx/boot.log')
        stream_stdout = (out / 'handoff-stream.stdout').open('wb')
        stream_stderr = (out / 'handoff-stream.stderr').open('wb')
        stream = subprocess.Popen(ssh_command(ip, stream_command),
                                  stdin=subprocess.DEVNULL,
                                  stdout=stream_stdout, stderr=stream_stderr)
        command = ('BB=/bin/busybox; '
                   'log() { printf "%s\\n" "$*" >> /run/lynx/boot.log; }; '
                   '. ' + REMOTE_LIB + '/autonomous-health-local-handoff.sh; '
                   'lynx_autonomous_health_local_handoff')
        _, rc = run('local-health-handoff', command, timeout=205)
        if rc:
            raise ValueError('Local handoff failed; independent phone timer remains armed')
        result, rc = run('health-postcheck',
                         'test -f /run/lynx/health-bootstrap/ready && '
                         '/bin/busybox sh /run/lynx/lynx-health-supervisor.sh --once && '
                         'cat /run/lynx/health-bootstrap-child.log', timeout=15)
        if rc or b'LYNX_HEALTH_OK' not in result:
            raise ValueError('Local health postcheck failed')
        _, rc = run('cancel-outer-timer',
                    'kill "$(cat /run/lynx/local-health-ram-timer.pid)" && '
                    'echo LOCAL_HEALTH_RAM_TIMER_CANCELLED')
        if rc:
            raise ValueError('Outer safety timer cancellation failed')
        protected = True
        report['state'] = 'local-health-in-ram-verified'
    except Exception as error:
        report.update(state='failed-or-refused', error=str(error))
        if timer_armed and not protected:
            try:
                state, _ = run('safety-state',
                               'if test -r /run/lynx/health-supervisor/pid && '
                               'kill -0 "$(cat /run/lynx/health-supervisor/pid)" 2>/dev/null; '
                               'then echo PROTECTED; else echo UNPROTECTED; fi')
                if b'UNPROTECTED' in state:
                    run('safe-poweroff-request', '/bin/busybox poweroff -f', timeout=6)
            except Exception as safety_error:
                report['safety_followup_error'] = str(safety_error)
        raise
    finally:
        if stream is not None and stream.poll() is None:
            stream.terminate()
            try:
                stream.wait(timeout=3)
            except subprocess.TimeoutExpired:
                stream.kill()
                stream.wait()
        if stream_stdout is not None:
            stream_stdout.close()
        if stream_stderr is not None:
            stream_stderr.close()
        stream_raw = out / 'handoff-stream.stdout'
        if stream_raw.exists():
            report['handoff_stream_bytes'] = stream_raw.stat().st_size
            report['handoff_stream_sha256'] = sha(stream_raw.read_bytes())
        report['finished_ns'] = time.time_ns()
        save(receipt, report)
        print(json.dumps({'state': report['state'], 'result': str(receipt)}))


if __name__ == '__main__':
    main()
