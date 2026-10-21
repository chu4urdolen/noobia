"""Find V34 by pinned host key and save repeated phone-side boot snapshots.

Bounded read-only Noobia WLAN discovery. Never updates known_hosts or
authenticates to a device whose public host key differs from Lynx's pin.
"""
import argparse
import asyncio
import json
import os
from pathlib import Path
import subprocess
import time

from find_lynx_pinned_ssh import NETWORK, pinned_key, probe
from lynx_wifi_v19_contact import ssh_command

ROOT = Path(__file__).resolve().parent.parent
CAPTURE = '''echo SAMPLE_BEGIN
date -u +%s
cat /proc/uptime /proc/sys/kernel/random/boot_id
readlink /proc/1/exe /proc/1/root
echo BOOT_LOG
cat /run/lynx/boot.log
echo BOOT_STATE
for p in /run/lynx/phase /run/lynx/bootstrap-result /run/lynx/worker-result /run/lynx/ssh-ready /run/lynx/local-boot-ready /run/lynx/health-bootstrap-child-result /run/lynx/health-bootstrap/ready /run/lynx/openrc-guard-last.log; do echo "$p"; cat "$p" 2>/dev/null; done
echo HEALTH_CHILD
cat /run/lynx/health-bootstrap-child.log 2>/dev/null
echo HEALTH_WATCHERS
cat /run/lynx/thermal-watch.log /run/lynx/battery-watch.log /run/lynx/thermal-cooling-watch.log /run/lynx/health-supervisor.log 2>/dev/null
echo PID1_STDIO
cat /run/lynx/openrc-pid1-stdout.log /run/lynx/openrc-pid1-stderr.log 2>/dev/null
echo BATTERY
cat /sys/bus/i2c/devices/7-0055/battery_snapshot 2>/dev/null
echo MOUNTS
cat /proc/mounts
echo END_SAMPLE
true'''


async def open_ssh_hosts():
    semaphore = asyncio.Semaphore(64)
    probes = [probe(ip, 22, semaphore) for ip in NETWORK.hosts()]
    return [ip for match in await asyncio.gather(*probes) if match for ip, _ in [match]]


def matching_host(hosts):
    expected = pinned_key()
    for ip in hosts:
        try:
            result = subprocess.run(['ssh-keyscan', '-T', '2', '-t', 'ed25519', ip],
                                    capture_output=True, text=True, timeout=4)
            if any(len(fields) >= 3 and fields[1:3] == expected
                   for fields in (line.split() for line in result.stdout.splitlines())
                   if fields):
                return ip
        except subprocess.TimeoutExpired:
            continue
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds', type=int, default=420)
    args = parser.parse_args()
    if not 1 <= args.seconds <= 900:
        parser.error('--seconds must be 1..900')
    os.umask(0o077)
    out = ROOT / 'logs' / ('v34-health-window-' + str(time.time_ns()))
    out.mkdir(mode=0o700)
    receipt = out / 'result.json'
    report = {'state': 'listening', 'created_ns': time.time_ns(),
              'seconds': args.seconds, 'phone_partition_writes': False,
              'pinned_ip': None, 'samples': []}

    def save():
        temporary = receipt.with_suffix('.tmp')
        temporary.write_text(json.dumps(report, indent=2) + '\n')
        temporary.replace(receipt)

    save(); print('V34 HEALTH COLLECTOR READY:', receipt, flush=True)
    start = time.monotonic()
    while time.monotonic() - start < args.seconds:
        report.update(heartbeat_ns=time.time_ns(),
                      elapsed_seconds=time.monotonic() - start)
        save()
        if report['pinned_ip'] is None:
            report['pinned_ip'] = matching_host(asyncio.run(open_ssh_hosts()))
            save()
            if report['pinned_ip'] is None:
                time.sleep(2); continue
            print('PINNED LYNX:', report['pinned_ip'], flush=True)
        item = {'started_ns': time.time_ns(), 'ip': report['pinned_ip']}
        report['samples'].append(item); save()
        path = out / ('sample-' + str(len(report['samples'])) + '.raw')
        try:
            result = subprocess.run(ssh_command(report['pinned_ip'], CAPTURE),
                                    capture_output=True, timeout=12)
            path.write_bytes(result.stdout + result.stderr)
            item.update(finished_ns=time.time_ns(), exit_code=result.returncode,
                        bytes=path.stat().st_size)
            if result.returncode != 0:
                report['pinned_ip'] = None
        except subprocess.TimeoutExpired as error:
            path.write_bytes((error.stdout or b'') + (error.stderr or b''))
            item.update(finished_ns=time.time_ns(), timed_out=True,
                        bytes=path.stat().st_size)
            report['pinned_ip'] = None
        save(); time.sleep(2)
    report.update(state='deadline', finished_ns=time.time_ns()); save()
    print(json.dumps({'state': report['state'], 'result': str(receipt),
                      'samples': len(report['samples'])}), flush=True)


if __name__ == '__main__':
    main()
