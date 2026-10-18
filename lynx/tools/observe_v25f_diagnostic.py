"""Capture candidate SSH contact and health transition without phone writes.

The pinned SSH host key plus image-specific /init hash identify Lynx. Every
attempt and every successful raw diagnostic is saved before parsing. No V19
acknowledgement, module load, reboot, or partition write is sent.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

from lynx_wifi_v19_contact import BUILD as V19_BUILD, beacon_valid, ssh_command

ROOT = Path(__file__).resolve().parent.parent
BUILDS = {
    'v25f': ROOT / 'linux-port/artifacts/selfboot-wifi-first-v25f-offline/build-result.json',
    'v25g': ROOT / 'linux-port/artifacts/selfboot-compact-v25g-offline/build-result.json',
    'v25h': ROOT / 'linux-port/artifacts/selfboot-beacon-v25h-offline/build-result.json',
    'v27a': ROOT / 'linux-port/artifacts/minimal-local-ssh-v27a-offline/build-result.json',
    'v28': ROOT / 'linux-port/artifacts/local-health-v28-offline/build-result.json',
}
PHONE_IP = '192.168.100.7'
PROBE = ("printf 'LYNX_V25F_PROBE\\n'; sha256sum /init /bin/busybox; "
         "uname -r; cat /proc/sys/kernel/random/boot_id; "
         "printf 'BOOTSTRAP='; cat /run/lynx/bootstrap-result 2>/dev/null || echo MISSING; "
         "printf 'SSH='; cat /run/lynx/ssh-ready 2>/dev/null || echo MISSING; "
         "printf 'WORKER='; cat /run/lynx/worker-result 2>/dev/null || echo MISSING; "
         "printf 'HEALTH='; cat /run/lynx/health-bootstrap/ready 2>/dev/null || echo MISSING; "
         "printf 'CHARGER\\n'; for f in /sys/class/power_supply/*/online; do "
         "[ -r \"$f\" ] && { printf '%s=' \"$f\"; cat \"$f\"; }; done; true")
DETAILS = ("printf 'UPTIME\\n'; cat /proc/uptime; "
           "printf 'BOOT_LOG\\n'; cat /run/lynx/boot.log; "
           "printf 'HEALTH_BOOT_LOG\\n'; cat /run/lynx/health-bootstrap-child.log 2>/dev/null; "
           "printf 'HEALTH_EVENTS\\n'; cat /run/lynx/health-supervisor/events.log 2>/dev/null; "
           "printf 'BATTERY\\n'; cat /run/lynx/battery-last 2>/dev/null; "
           "printf 'THERMAL\\n'; tail -n 10 /run/lynx/thermal-watch.log 2>/dev/null; "
           "printf 'COOLING\\n'; tail -n 10 /run/lynx/thermal-cooling-watch.log 2>/dev/null; true")
KERNEL = "dmesg"
BUSYBOX_SHA = '999cb969d09093a71716cfc747bb53cdada3f332c05eb5046c56e0f66a4d6d22'


def parse_proof(raw, expected):
    lines = raw.decode(errors='replace').splitlines()
    if (len(lines) < 11 or lines[0] != 'LYNX_V25F_PROBE' or
            lines[1] != expected + '  /init' or
            lines[2] != BUSYBOX_SHA + '  /bin/busybox' or
            lines[3] != '5.10.149-android12-9-o-g311738fbb5a8' or
            not lines[5].startswith('BOOTSTRAP=') or
            not lines[6].startswith('SSH=') or
            not lines[7].startswith('WORKER=') or
            not lines[8].startswith('HEALTH=')):
        return None
    supplies = [line for line in lines[10:] if line.startswith('/sys/class/power_supply/')
                and '/online=' in line]
    if not supplies or any(not line.endswith('=0') for line in supplies):
        return None
    values = {key: lines[index].split('=', 1)[1] for key, index in
              [('bootstrap', 5), ('ssh', 6), ('worker', 7), ('health', 8)]}
    if values['bootstrap'] != '0' or values['ssh'] != 'ready' or values['worker'] != '0':
        return None
    return {'boot_id': lines[4], 'health_ready': values['health'] == 'ready',
            'health_value': values['health'], 'offline_supplies': len(supplies)}


def save(path, report):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(report, indent=2) + '\n')
    tmp.replace(path)


def ssh_capture(out, name, command, phone_ip, timeout=12):
    started = time.time_ns()
    try:
        result = subprocess.run(ssh_command(phone_ip, command), capture_output=True, timeout=timeout)
        stdout, stderr, code = result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired as error:
        stdout, stderr, code = error.stdout or b'', error.stderr or b'', None
    (out / (name + '.stdout')).write_bytes(stdout)
    (out / (name + '.stderr')).write_bytes(stderr)
    return stdout, {'name': name, 'phone_ip': phone_ip,
                    'started_ns': started, 'finished_ns': time.time_ns(),
                    'exit_code': code, 'stdout_sha256': hashlib.sha256(stdout).hexdigest(),
                    'stderr_sha256': hashlib.sha256(stderr).hexdigest()}


def worker(out):
    receipt = out / 'result.json'
    report = json.loads(receipt.read_text())
    expected = report['expected_init_sha256']
    deadline = time.monotonic() + report['seconds']
    first_kernel_saved = False
    attempt = 0
    phone_ip = PHONE_IP
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as beacon_socket:
        beacon_socket.bind((V19_BUILD['collector_ip'], 5514))
        beacon_socket.setblocking(False)
        report.update(state='listening', ready_ns=time.time_ns(),
                      beacon_bind_ip=V19_BUILD['collector_ip'], beacon_port=5514,
                      current_probe_ip=phone_ip, valid_beacons=[])
        save(receipt, report)
        while time.monotonic() < deadline:
            while True:
                try:
                    datagram, address = beacon_socket.recvfrom(4096)
                except BlockingIOError:
                    break
                event = {'received_ns': time.time_ns(), 'source_ip': address[0],
                         'bytes': len(datagram), 'sha256': hashlib.sha256(datagram).hexdigest(),
                         'valid': beacon_valid(datagram, address[0])}
                with (out / 'beacons.jsonl').open('a') as journal:
                    journal.write(json.dumps(event) + '\n')
                if event['valid']:
                    phone_ip = address[0]
                    report['current_probe_ip'] = phone_ip
                    report['valid_beacons'].append(event)
                    save(receipt, report)
            report['heartbeat_ns'] = time.time_ns()
            save(receipt, report)
            raw, event = ssh_capture(out, f'probe-{attempt:04d}', PROBE, phone_ip)
            proof = parse_proof(raw, expected) if event['exit_code'] == 0 else None
            event['candidate_early_identity'] = proof is not None
            event['health_ready'] = proof['health_ready'] if proof else False
            with (out / 'attempts.jsonl').open('a') as journal:
                journal.write(json.dumps(event) + '\n')
            report.update(attempts=attempt + 1, last_attempt=event)
            if proof:
                if not report.get('early_ssh_verified'):
                    report.update(state='early-ssh-verified', early_ssh_verified=True,
                                  first_ssh_ns=time.time_ns(), boot_id=proof['boot_id'])
                if proof['boot_id'] != report['boot_id']:
                    report.update(state='boot-id-changed', finished_ns=time.time_ns())
                    save(receipt, report)
                    return
                _, detail_event = ssh_capture(out, f'details-{attempt:04d}', DETAILS, phone_ip, timeout=20)
                report['last_details'] = detail_event
                if not first_kernel_saved:
                    _, kernel_event = ssh_capture(out, 'first-kernel', KERNEL, phone_ip, timeout=20)
                    report['first_kernel'] = kernel_event
                    first_kernel_saved = True
                if report['candidate'] == 'v27a':
                    report.update(state='v27a-early-ssh-verified', native_ssh_verified=True,
                                  finished_ns=time.time_ns())
                    save(receipt, report)
                    return
                if proof['health_ready']:
                    report.update(state=report['candidate'] + '-health-ready', native_ssh_verified=True,
                                  health_verified_ns=time.time_ns(), finished_ns=time.time_ns())
                    save(receipt, report)
                    return
            save(receipt, report)
            attempt += 1
            time.sleep(min(3, max(0, deadline - time.monotonic())))
    report.update(state='deadline-without-health-proof', finished_ns=time.time_ns())
    save(receipt, report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument('--arm', action='store_true')
    actions.add_argument('--worker', type=Path)
    actions.add_argument('--self-test', action='store_true')
    parser.add_argument('--seconds', type=int, default=900)
    parser.add_argument('--candidate', choices=sorted(BUILDS), default='v25f')
    args = parser.parse_args()
    manifest = json.loads(BUILDS[args.candidate].read_text())
    init_sha = manifest.get('new_init_sha256', manifest.get('init_sha256'))
    image_name = {
        'v25f': 'nord3-selfboot-health-untested.img',
        'v25g': 'nord3-selfboot-compact-untested.img',
        'v25h': 'nord3-selfboot-beacon-untested.img',
        'v27a': 'nord3-minimal-local-ssh-untested.img',
        'v28': 'nord3-local-health-untested.img',
    }[args.candidate]
    if not init_sha or manifest['image_sha256'] != hashlib.sha256(
            (BUILDS[args.candidate].parent / image_name).read_bytes()).hexdigest():
        raise ValueError('Candidate image differs from pinned manifest')
    if args.self_test:
        raw = ('LYNX_V25F_PROBE\n' + init_sha + '  /init\n' +
               BUSYBOX_SHA + '  /bin/busybox\n' +
               '5.10.149-android12-9-o-g311738fbb5a8\nboot-id\n' +
               'BOOTSTRAP=0\nSSH=ready\nWORKER=0\nHEALTH=MISSING\nCHARGER\n' +
               '/sys/class/power_supply/charger/online=0\n').encode()
        assert parse_proof(raw, init_sha) == {
            'boot_id': 'boot-id', 'health_ready': False,
            'health_value': 'MISSING', 'offline_supplies': 1}
        assert parse_proof(raw.replace(b'HEALTH=MISSING', b'HEALTH=ready'),
                           init_sha)['health_ready']
        assert parse_proof(raw.replace(b'online=0', b'online=1'),
                           init_sha) is None
        assert parse_proof(raw.replace(init_sha.encode(), b'0'*64), init_sha) is None
        assert beacon_valid(('LYNX_HELLO ' + V19_BUILD['session_token']).encode(), PHONE_IP)
        assert not beacon_valid(b'LYNX_HELLO wrong', PHONE_IP)
        print(args.candidate + ' identity and beacon parser passed; no phone contacted.')
        return
    if args.worker:
        worker(args.worker.resolve(strict=True))
        return
    if not 30 <= args.seconds <= 1800:
        parser.error('--seconds must be 30..1800')
    os.umask(0o077)
    out = ROOT / 'logs' / (args.candidate + '-diagnostic-observer-' + str(time.time_ns()))
    out.mkdir(mode=0o700)
    report = {'state': 'starting', 'created_ns': time.time_ns(),
              'seconds': args.seconds, 'phone_ip': PHONE_IP, 'candidate': args.candidate,
              'expected_init_sha256': init_sha,
              'image_sha256': manifest['image_sha256'],
              'phone_writes': False, 'flash_performed': False,
              'tool_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    save(out / 'result.json', report)
    with (out / 'worker.stdout').open('wb') as stdout, (out / 'worker.stderr').open('wb') as stderr:
        child = subprocess.Popen([sys.executable, str(Path(__file__).resolve()),
                                  '--worker', str(out), '--candidate', args.candidate],
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
