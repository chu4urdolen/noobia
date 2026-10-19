"""Poll pinned rescue SSH for a fresh V34 boot; save one broad capture.

V34 does not require a host acknowledgement. This tool is read-only on Lynx.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from lynx_wifi_v19_contact import KERNEL, BB_SHA, ssh_command

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / 'linux-port/artifacts/local-persistent-alpine-v34-offline/build-result.json'
IMAGE = ROOT / 'linux-port/artifacts/local-persistent-alpine-v34-offline/nord3-local-persistent-alpine-v34-untested.img'
IP = '192.168.100.4'
PROOF = "printf 'LYNX_V34_PROOF\\n'; uname -r; readlink /proc/1/exe; sha256sum /init /bin/busybox; cat /proc/sys/kernel/random/boot_id; cat /etc/lynx/session-token; id"
DIAGNOSTICS = '''printf 'BOOT_LOG\\n'; cat /run/lynx/boot.log
printf 'PID1_LOGS\\n'; cat /run/lynx/openrc-pid1-stdout.log /run/lynx/openrc-pid1-stderr.log 2>/dev/null
printf 'HEALTH_LOGS\\n'; cat /run/lynx/health-bootstrap-child.log /run/lynx/health-supervisor.log /run/lynx/thermal-cooling-watch.log 2>/dev/null
printf 'BOOT_MARKERS\\n'; for p in /run/lynx/bootstrap-result /run/lynx/worker-result /run/lynx/ssh-ready /run/lynx/health-bootstrap/ready; do echo "$p"; cat "$p" 2>/dev/null; done
printf 'PID1_ROOT\\n'; readlink /proc/1/root /proc/1/exe
printf 'OPENRC\\n'; /bin/busybox chroot /run/lynx/persistent-alpine /bin/rc-status -a 2>/dev/null
printf 'NETWORK\\n'; ip addr; ip route; netstat -lnt
printf 'MOUNTS\\n'; cat /proc/mounts
printf 'PSTORE\\n'; for p in /sys/fs/pstore/*; do [ -f "$p" ] && { echo "$p"; cat "$p"; }; done
true'''


def sha(data):
    return hashlib.sha256(data).hexdigest()


def proof_ok(raw, code, expected_init, token):
    text = raw.decode(errors='replace')
    return (code == 0 and 'LYNX_V34_PROOF\n' in text and KERNEL + '\n' in text and
            expected_init + '  /init' in text and BB_SHA + '  /bin/busybox' in text and
            token + '\n' in text and 'uid=0(root)' in text and
            ('/bin/busybox\n' in text or
             '/run/lynx/persistent-alpine/sbin/openrc-init\n' in text))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--listen', action='store_true')
    parser.add_argument('--seconds', type=int, default=600)
    args = parser.parse_args()
    build = json.loads(BUILD.read_text())
    image_sha = sha(IMAGE.read_bytes())
    if (build.get('state') != 'offline-autonomous-alpine-candidate-built' or
            image_sha != build['image_sha256']):
        raise ValueError('V34 image provenance differs')
    v19 = json.loads((ROOT / 'linux-port/artifacts/busybox-wifi-ssh-twostage-v19/build-validation.json').read_text())
    if not args.listen:
        print(json.dumps({'state': 'offline-ready', 'image_sha256': image_sha,
                          'phone_contacted': False, 'partition_writes': False}))
        return
    if not 1 <= args.seconds <= 900:
        parser.error('--seconds must be 1..900')
    os.umask(0o077)
    out = ROOT / 'logs' / ('v34-contact-' + str(time.time_ns()))
    out.mkdir(mode=0o700)
    receipt = out / 'result.json'
    report = {'state': 'listening', 'created_ns': time.time_ns(),
              'created_monotonic': time.monotonic(), 'seconds': args.seconds,
              'image_sha256': image_sha, 'phone_ip': IP,
              'expected_init_sha256': build['init_sha256'],
              'partition_writes': False, 'events': []}

    def save():
        tmp = receipt.with_suffix('.tmp')
        tmp.write_text(json.dumps(report, indent=2) + '\n')
        tmp.replace(receipt)

    save()
    print('V34 CONTACT READY:', receipt, flush=True)
    start = time.monotonic()
    while time.monotonic() - start < args.seconds:
        report.update(heartbeat_ns=time.time_ns(),
                      heartbeat_monotonic=time.monotonic(),
                      elapsed_seconds=time.monotonic() - start)
        save()
        event = {'started_ns': time.time_ns(), 'started_monotonic': time.monotonic()}
        report['events'].append(event); save()
        try:
            result = subprocess.run(ssh_command(IP, PROOF), capture_output=True, timeout=12)
        except subprocess.TimeoutExpired as error:
            event.update(state='timeout', finished_ns=time.time_ns())
            (out / ('proof-' + str(len(report['events'])) + '.raw')).write_bytes(
                (error.stdout or b'') + (error.stderr or b''))
            save(); time.sleep(2); continue
        raw = result.stdout + result.stderr
        (out / ('proof-' + str(len(report['events'])) + '.raw')).write_bytes(raw)
        event.update(state='returned', finished_ns=time.time_ns(),
                     exit_code=result.returncode, raw_sha256=sha(raw))
        if proof_ok(result.stdout, result.returncode, build['init_sha256'], v19['session_token']):
            report.update(state='v34-pinned-ssh-verified', verified_ns=time.time_ns(),
                          proof_event=len(report['events']))
            save()
            try:
                diag = subprocess.run(ssh_command(IP, DIAGNOSTICS), capture_output=True,
                                      timeout=35)
                (out / 'diagnostics.raw').write_bytes(diag.stdout + diag.stderr)
                report['diagnostics_exit_code'] = diag.returncode
            except subprocess.TimeoutExpired as error:
                (out / 'diagnostics.raw').write_bytes((error.stdout or b'') + (error.stderr or b''))
                report['diagnostics_timed_out'] = True
            report['finished_ns'] = time.time_ns(); save()
            print(json.dumps({'state': report['state'], 'result': str(receipt)}), flush=True)
            return
        save(); time.sleep(2)
    report.update(state='deadline-without-v34-ssh', finished_ns=time.time_ns())
    save()
    print(json.dumps({'state': report['state'], 'result': str(receipt)}), flush=True)
    raise SystemExit(1)


if __name__ == '__main__':
    main()
