"""Set Lynx's uninitialized wall clock from Nexus's synchronized UTC clock."""

import json
import os
from pathlib import Path
import subprocess
import time

from lynx_wifi_v19_contact import ssh_command


ROOT = Path(__file__).resolve().parent.parent
IP = '192.168.100.8'
BOOT_ID = 'f6230cac-8d41-48da-bf28-2700e9ff56f1'


def call(command):
    argv = ssh_command(IP, command)
    argv[-2:-2] = ['-p', '2222']
    return subprocess.run(argv, capture_output=True, timeout=12)


def main():
    os.umask(0o077)
    out = ROOT / 'logs' / f'v46-clock-seed-{time.time_ns()}'
    out.mkdir(mode=0o700)
    report = {'state': 'starting', 'phone_ip': IP, 'boot_id': BOOT_ID,
              'boot_partition_writes': False, 'source': 'Nexus synchronized UTC'}
    try:
        sync = subprocess.run(['timedatectl', 'show', '-p', 'NTPSynchronized', '--value'],
                              capture_output=True, text=True, check=True, timeout=3)
        if sync.stdout.strip() != 'yes':
            raise RuntimeError('Nexus clock is not NTP synchronized')
        pre = call('cat /proc/sys/kernel/random/boot_id; date -u +%s')
        (out / 'pre.stdout').write_bytes(pre.stdout)
        (out / 'pre.stderr').write_bytes(pre.stderr)
        parts = pre.stdout.decode().splitlines()
        if pre.returncode or len(parts) != 2 or parts[0] != BOOT_ID or int(parts[1]) > 946684800:
            raise RuntimeError('Phone is not the expected boot with unset clock')
        epoch = int(time.time())
        report.update(previous_epoch=int(parts[1]), nexus_epoch=epoch)
        set_clock = call(f'set -eu; test "$(cat /proc/sys/kernel/random/boot_id)" = "{BOOT_ID}"; '
                         f'date -u -s @{epoch}; date -u +%s')
        (out / 'set.stdout').write_bytes(set_clock.stdout)
        (out / 'set.stderr').write_bytes(set_clock.stderr)
        if set_clock.returncode:
            raise RuntimeError('Setting clock failed')
        actual = int(set_clock.stdout.decode().splitlines()[-1])
        if abs(actual - int(time.time())) > 10:
            raise RuntimeError('Clock verification differs by over 10 seconds')
        report.update(state='v46-clock-seeded-from-synchronized-nexus', verified_epoch=actual)
    except Exception as exc:
        report.update(state='failed-or-incomplete', error=str(exc))
    report['finished_ns'] = time.time_ns()
    receipt = out / 'result.json'
    receipt.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'state': report['state'], 'result': str(receipt)}))
    if report['state'] != 'v46-clock-seeded-from-synchronized-nexus':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
