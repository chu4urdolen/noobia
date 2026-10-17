"""Bounded, detached, read-only observer for one V25d unplugged boot.

Uses Lynx's pinned SSH key. It never acknowledges V19, writes the phone,
reboots it, or treats a black screen as proof of power state.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from lynx_wifi_v19_contact import ssh_command

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / 'linux-port/artifacts/selfboot-health-v25d-offline/build-result.json'
PHONE_IP = '192.168.100.7'
PROBE = ("printf 'LYNX_V25D_PROBE\\n'; sha256sum /init /bin/busybox; "
         "cat /proc/sys/kernel/random/boot_id; uname -r; "
         "cat /run/lynx/bootstrap-result /run/lynx/health-bootstrap/ready "
         "/run/lynx/ssh-ready /run/lynx/worker-result 2>/dev/null; "
         "cat /run/lynx/battery-last 2>/dev/null; "
         "for f in /sys/class/power_supply/*/online; do [ -r \"$f\" ] && "
         "{ printf '%s=' \"$f\"; cat \"$f\"; }; done; true")
DETAILS = ("printf 'BOOT_LOG\\n'; cat /run/lynx/boot.log; "
           "printf 'HEALTH_BOOT_LOG\\n'; cat /run/lynx/health-bootstrap-child.log; "
           "printf 'HEALTH_EVENTS\\n'; cat /run/lynx/health-supervisor/events.log; "
           "printf 'BATTERY\\n'; cat /run/lynx/battery-last; "
           "printf 'THERMAL\\n'; cat /run/lynx/thermal-watch.log; "
           "printf 'COOLING\\n'; cat /run/lynx/thermal-cooling-watch.log; "
           "printf 'NETWORK\\n'; ip addr; ip route; "
           "printf 'KERNEL\\n'; dmesg; true")


def valid_proof(raw, expected):
    text = raw.decode(errors='replace')
    lines = text.splitlines()
    supplies = [line for line in lines if line.startswith('/sys/class/power_supply/')
                and '/online=' in line]
    return (len(lines) >= 9 and lines[0] == 'LYNX_V25D_PROBE' and
            lines[1] == expected + '  /init' and
            lines[2] == '999cb969d09093a71716cfc747bb53cdada3f332c05eb5046c56e0f66a4d6d22  /bin/busybox' and
            lines[4] == '5.10.149-android12-9-o-g311738fbb5a8' and
            lines[5:9] == ['0', 'ready', 'ready', '0'] and
            bool(supplies) and all(line.endswith('=0') for line in supplies))


def save(path, report):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(report, indent=2) + '\n')
    temp.replace(path)


def worker(out):
    manifest = json.loads(BUILD.read_text())
    expected = manifest['new_init_sha256']
    receipt = out / 'result.json'
    report = json.loads(receipt.read_text())
    report.update(state='listening', ready_ns=time.time_ns(), heartbeat_ns=time.time_ns())
    save(receipt, report)
    deadline = time.monotonic() + report['seconds']
    attempt = 0
    while time.monotonic() < deadline:
        report['heartbeat_ns'] = time.time_ns()
        save(receipt, report)
        name = f'probe-{attempt:04d}'
        started = time.time_ns()
        try:
            result = subprocess.run(ssh_command(PHONE_IP, PROBE), capture_output=True, timeout=10)
            stdout, stderr, code = result.stdout, result.stderr, result.returncode
        except subprocess.TimeoutExpired as error:
            stdout, stderr, code = error.stdout or b'', error.stderr or b'', None
        (out / (name + '.stdout')).write_bytes(stdout)
        (out / (name + '.stderr')).write_bytes(stderr)
        event = {'attempt': attempt, 'started_ns': started,
                 'finished_ns': time.time_ns(), 'exit_code': code,
                 'stdout_sha256': hashlib.sha256(stdout).hexdigest(),
                 'stderr_sha256': hashlib.sha256(stderr).hexdigest(),
                 'candidate_proof': code == 0 and valid_proof(stdout, expected)}
        with (out / 'attempts.jsonl').open('a') as stream:
            stream.write(json.dumps(event) + '\n')
        report.update(attempts=attempt + 1, last_attempt=event)
        save(receipt, report)
        if event['candidate_proof']:
            report.update(state='v25d-identity-and-health-ready',
                          native_ssh_verified=True, verified_ns=time.time_ns(),
                          proof_file=str(out / (name + '.stdout')))
            save(receipt, report)
            try:
                detail = subprocess.run(ssh_command(PHONE_IP, DETAILS), capture_output=True, timeout=35)
                (out / 'details.stdout').write_bytes(detail.stdout)
                (out / 'details.stderr').write_bytes(detail.stderr)
                report['details_exit_code'] = detail.returncode
            except subprocess.TimeoutExpired as error:
                (out / 'details.stdout').write_bytes(error.stdout or b'')
                (out / 'details.stderr').write_bytes(error.stderr or b'')
                report['details_timed_out'] = True
            report['finished_ns'] = time.time_ns()
            save(receipt, report)
            return
        attempt += 1
        time.sleep(min(5, max(0, deadline - time.monotonic())))
    report.update(state='deadline-without-v25d-proof', finished_ns=time.time_ns())
    save(receipt, report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument('--arm', action='store_true')
    actions.add_argument('--worker', type=Path)
    actions.add_argument('--self-test', action='store_true')
    parser.add_argument('--seconds', type=int, default=900)
    args = parser.parse_args()
    manifest = json.loads(BUILD.read_text())
    if args.self_test:
        expected = manifest['new_init_sha256']
        sample = ('LYNX_V25D_PROBE\n' + expected + '  /init\n' +
                  '999cb969d09093a71716cfc747bb53cdada3f332c05eb5046c56e0f66a4d6d22  /bin/busybox\n' + 'boot-id\n' +
                  '5.10.149-android12-9-o-g311738fbb5a8\n' +
                  '0\nready\nready\n0\n' +
                  '/sys/class/power_supply/mt6375-charger/online=0\n').encode()
        assert valid_proof(sample, expected)
        assert not valid_proof(sample.replace(b'online=0', b'online=1'), expected)
        assert not valid_proof(sample.replace(expected.encode(), b'0'*64), expected)
        print('V25d proof parser passed; no handset contacted.')
        return
    if args.worker:
        worker(args.worker.resolve(strict=True))
        return
    if not 30 <= args.seconds <= 900:
        parser.error('--seconds must be 30..900')
    os.umask(0o077)
    out = ROOT / 'logs' / ('v25d-selfboot-observer-' + str(time.time_ns()))
    out.mkdir(mode=0o700)
    report = {'state': 'starting', 'created_ns': time.time_ns(),
              'seconds': args.seconds, 'phone_ip': PHONE_IP,
              'expected_init_sha256': manifest['new_init_sha256'],
              'image_sha256': manifest['image_sha256'],
              'phone_writes': False, 'flash_performed': False,
              'tool_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    save(out / 'result.json', report)
    with (out / 'worker.stdout').open('wb') as stdout, (out / 'worker.stderr').open('wb') as stderr:
        child = subprocess.Popen([sys.executable, str(Path(__file__).resolve()),
                                  '--worker', str(out)],
                                 stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                                 start_new_session=True, cwd=ROOT)
    for _ in range(100):
        report = json.loads((out / 'result.json').read_text())
        if report['state'] == 'listening':
            print(json.dumps({'state': 'ready-before-physical-step',
                              'result': str(out / 'result.json'), 'pid': child.pid}))
            return
        if child.poll() is not None:
            raise SystemExit('Observer exited before readiness: ' + str(out))
        time.sleep(.1)
    raise SystemExit('Observer did not become ready: ' + str(out))


if __name__ == '__main__':
    main()
