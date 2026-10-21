"""Capture repeated read-only V38 snapshots after pinned SSH appears."""
import argparse
import asyncio
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import time

from capture_v34_health_window import CAPTURE, matching_host, open_ssh_hosts
from lynx_wifi_v19_contact import ssh_command

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / 'linux-port/artifacts/persistent-trace-v38-offline/build-result.json'
IMAGE = ROOT / 'linux-port/artifacts/persistent-trace-v38-offline/nord3-persistent-trace-v38-untested.img'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds', type=int, default=420)
    parser.add_argument('--interval', type=float, default=2.0,
                        help='seconds between completed snapshots (default: 2)')
    args = parser.parse_args()
    if not 1 <= args.seconds <= 900:
        parser.error('--seconds must be 1..900')
    if not math.isfinite(args.interval) or not 0.5 <= args.interval <= 30:
        parser.error('--interval must be finite and 0.5..30 seconds')
    build = json.loads(BUILD.read_text())
    if (build['state'] != 'offline-persistent-trace-diagnostic-built' or
            hashlib.sha256(IMAGE.read_bytes()).hexdigest() != build['image_sha256']):
        raise ValueError('V38 image differs')
    os.umask(0o077)
    out = ROOT / 'logs' / ('v38-persistent-window-' + str(time.time_ns()))
    out.mkdir(mode=0o700)
    receipt = out / 'result.json'
    report = {'state': 'listening', 'created_ns': time.time_ns(),
              'image_sha256': build['image_sha256'],
              'expected_init_sha256': build['init_sha256'],
              'seconds': args.seconds, 'interval_seconds': args.interval,
              'phone_partition_writes': False,
              'pinned_ip': None, 'candidate_seen': False, 'samples': [],
              'collector_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    stop_requested = False

    def request_stop(signum, frame):
        nonlocal stop_requested
        stop_requested = True

    signal.signal(signal.SIGINT, request_stop)

    def save():
        temp = receipt.with_suffix('.tmp')
        temp.write_text(json.dumps(report, indent=2) + '\n')
        temp.replace(receipt)

    save()
    print('V38 PERSISTENT COLLECTOR READY:', receipt, flush=True)
    start = time.monotonic()
    capture = "printf 'INIT_SHA\\n'; sha256sum /init; " + CAPTURE
    while not stop_requested and time.monotonic() - start < args.seconds:
        report.update(heartbeat_ns=time.time_ns(),
                      elapsed_seconds=time.monotonic() - start)
        save()
        if report['pinned_ip'] is None:
            report['pinned_ip'] = matching_host(asyncio.run(open_ssh_hosts()))
            save()
            if report['pinned_ip'] is None:
                time.sleep(args.interval)
                continue
            print('PINNED LYNX:', report['pinned_ip'], flush=True)
        item = {'started_ns': time.time_ns(), 'ip': report['pinned_ip']}
        report['samples'].append(item)
        save()
        path = out / ('sample-' + str(len(report['samples'])) + '.raw')
        try:
            result = subprocess.run(ssh_command(report['pinned_ip'], capture),
                                    capture_output=True, timeout=12)
            raw = result.stdout + result.stderr
            path.write_bytes(raw)
            item.update(finished_ns=time.time_ns(), exit_code=result.returncode,
                        bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(),
                        v38_init_match=(build['init_sha256'].encode() + b'  /init')
                        in result.stdout)
            if item['v38_init_match'] and result.returncode == 0:
                report['candidate_seen'] = True
            if result.returncode:
                report['pinned_ip'] = None
        except subprocess.TimeoutExpired as error:
            raw = (error.stdout or b'') + (error.stderr or b'')
            path.write_bytes(raw)
            item.update(finished_ns=time.time_ns(), timed_out=True, bytes=len(raw))
            report['pinned_ip'] = None
        save()
        time.sleep(args.interval)
    report.update(state='interrupted' if stop_requested else 'deadline',
                  finished_ns=time.time_ns())
    save()
    print(json.dumps({'state': report['state'], 'result': str(receipt),
                      'candidate_seen': report['candidate_seen'],
                      'samples': len(report['samples'])}), flush=True)


if __name__ == '__main__':
    main()
