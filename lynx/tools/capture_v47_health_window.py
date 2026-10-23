"""Observe a future V47 boot over pinned rescue SSH without phone writes."""

import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import time

from capture_v34_health_window import matching_host, open_ssh_hosts
from lynx_wifi_v19_contact import ssh_command


ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'linux-port/artifacts/wifi-dhcp-retry-v47-offline'
IMAGE = OUT / 'nord3-wifi-dhcp-retry-v47-untested.img'
IMAGE_SHA = 'c969e1938b051ab03b49ad4f2260e900e9e336997d1026ca00c3a493dedde066'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds', type=int, default=600)
    parser.add_argument('--interval', type=float, default=2.0)
    args = parser.parse_args()
    if not 1 <= args.seconds <= 900 or not 0.5 <= args.interval <= 30:
        parser.error('seconds must be 1..900 and interval 0.5..30')
    build = json.loads((OUT / 'build-result.json').read_text())
    validation = json.loads((OUT / 'validation.json').read_text())
    if (build.get('state') != 'offline-v47-dhcp-retry-candidate-built' or
            validation.get('state') != 'offline-v47-validation-passed' or
            build.get('image_sha256') != IMAGE_SHA or
            validation.get('image_sha256') != IMAGE_SHA or
            hashlib.sha256(IMAGE.read_bytes()).hexdigest() != IMAGE_SHA):
        raise ValueError('V47 image or validation differs')
    os.umask(0o077)
    out = ROOT / 'logs' / f'v47-health-window-{time.time_ns()}'
    out.mkdir(mode=0o700)
    receipt = out / 'result.json'
    report = {'state': 'listening', 'created_ns': time.time_ns(),
              'image_sha256': IMAGE_SHA,
              'expected_init_sha256': build['init_sha256'],
              'expected_wifi_sha256': build['new_wifi_sha256'],
              'phone_partition_writes': False, 'pinned_ip': None,
              'candidate_seen': False, 'alpine_pid1_seen': False,
              'samples': []}
    interrupted = False

    def stop(_signum, _frame):
        nonlocal interrupted
        interrupted = True

    signal.signal(signal.SIGINT, stop)

    def save():
        temp = receipt.with_suffix('.tmp')
        temp.write_text(json.dumps(report, indent=2) + '\n')
        temp.replace(receipt)

    save()
    print('V47 COLLECTOR READY:', receipt, flush=True)
    started = time.monotonic()
    capture = (
        'printf "BOOT_ID="; cat /proc/sys/kernel/random/boot_id; '
        'printf "INIT_SHA\\n"; sha256sum /init; '
        'printf "WIFI_SHA\\n"; sha256sum /etc/lynx/wifi-runtime.sh; '
        'printf "PID1_EXE="; readlink /proc/1/exe; '
        'printf "ALPINE_RELEASE="; cat /proc/1/root/etc/alpine-release 2>/dev/null || true; '
        'printf "UPTIME="; cat /proc/uptime; '
        'printf "BATTERY\\n"; cat /sys/bus/i2c/devices/7-0055/battery_snapshot 2>/dev/null || true; '
        'printf "BOOT_LOG\\n"; tail -n 30 /run/lynx/boot.log 2>/dev/null || true'
    )
    while not interrupted and time.monotonic() - started < args.seconds:
        report.update(heartbeat_ns=time.time_ns(),
                      elapsed_seconds=time.monotonic() - started)
        save()
        if report['pinned_ip'] is None:
            report['pinned_ip'] = matching_host(asyncio.run(open_ssh_hosts()))
            save()
            if report['pinned_ip'] is None:
                time.sleep(args.interval)
                continue
        item = {'started_ns': time.time_ns(), 'ip': report['pinned_ip']}
        report['samples'].append(item)
        save()
        path = out / f'sample-{len(report["samples"])}.raw'
        try:
            run = subprocess.run(ssh_command(report['pinned_ip'], capture),
                                 capture_output=True, timeout=12)
            raw = run.stdout + run.stderr
            path.write_bytes(raw)
            init_match = (build['init_sha256'].encode() + b'  /init') in run.stdout
            wifi_match = (build['new_wifi_sha256'].encode() +
                          b'  /etc/lynx/wifi-runtime.sh') in run.stdout
            alpine = (b'PID1_EXE=/run/lynx/persistent-alpine/sbin/openrc-init'
                      in run.stdout and b'ALPINE_RELEASE=3.24.2' in run.stdout)
            item.update(finished_ns=time.time_ns(), exit_code=run.returncode,
                        bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(),
                        init_match=init_match, wifi_match=wifi_match,
                        alpine_pid1_match=alpine)
            if run.returncode == 0 and init_match and wifi_match:
                report['candidate_seen'] = True
                if alpine:
                    report['alpine_pid1_seen'] = True
            if run.returncode:
                report['pinned_ip'] = None
        except subprocess.TimeoutExpired as exc:
            raw = (exc.stdout or b'') + (exc.stderr or b'')
            path.write_bytes(raw)
            item.update(finished_ns=time.time_ns(), timed_out=True,
                        bytes=len(raw))
            report['pinned_ip'] = None
        save()
        time.sleep(args.interval)
    report.update(state='interrupted' if interrupted else 'deadline',
                  finished_ns=time.time_ns())
    save()
    print(json.dumps({'state': report['state'], 'result': str(receipt),
                      'candidate_seen': report['candidate_seen'],
                      'alpine_pid1_seen': report['alpine_pid1_seen'],
                      'samples': len(report['samples'])}), flush=True)


if __name__ == '__main__':
    main()
