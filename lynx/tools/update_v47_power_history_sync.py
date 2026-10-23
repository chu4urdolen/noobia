"""Flush each Lynx power-history sample without changing its old log file."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from lynx_wifi_v19_contact import ssh_command


ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / 'linux-port/lynx-power-history.sh'
IP = '192.168.100.8'
BOOT_ID = '9054078d-aafa-4abf-9600-5c70f8234360'
OLD_SHA = '97e84e17e8bdf05900a01533fc91ad4422221a78d5b1d4ba824a8269dda61dff'
INIT_SHA = 'ebc6bb746aaf710d915c47036f92ce0c4ed23a185dfb5349b90e654bab7ba4ae'
WIFI_SHA = 'be24ce67cbaefef63db0ba65badb69df1a2b45bb3f743e8f3877509eaf972208'


def main():
    subprocess.run(['/bin/sh', '-n', str(SOURCE)], check=True)
    data = SOURCE.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    os.umask(0o077)
    out = ROOT / 'logs' / f'v47-power-history-sync-{time.time_ns()}'
    out.mkdir(mode=0o700)
    report = {'state': 'starting', 'boot_id': BOOT_ID, 'phone_ip': IP,
              'old_sha256': OLD_SHA, 'new_sha256': digest,
              'boot_partition_writes': False, 'steps': []}

    def step(name, command, payload=None, timeout=25, port=2222):
        argv = ssh_command(IP, command)
        argv[-2:-2] = ['-p', str(port)]
        run = subprocess.run(argv, input=payload, capture_output=True, timeout=timeout)
        (out / f'{name}.stdout').write_bytes(run.stdout)
        (out / f'{name}.stderr').write_bytes(run.stderr)
        report['steps'].append({'name': name, 'exit_code': run.returncode,
                                'stdout_sha256': hashlib.sha256(run.stdout).hexdigest()})
        if run.returncode:
            raise RuntimeError(f'{name} failed; see saved streams')
        return run.stdout.decode(errors='replace')

    target = '/usr/libexec/lynx-power-history.sh'
    backup = '/root/lynx-rescue/lynx-power-history-before-fsync-v47.sh'
    staged = '/run/lynx/lynx-power-history-fsync.new'
    backup_created = False
    try:
        step('rescue_identity',
             'set -eu; '
             f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{BOOT_ID}"; '
             f'test "$(sha256sum /init | cut -c1-64)" = "{INIT_SHA}"; '
             f'test "$(sha256sum /etc/lynx/wifi-runtime.sh | cut -c1-64)" = "{WIFI_SHA}"; '
             'printf LYNX_V47_RESCUE_IDENTITY', port=22)
        step('preflight',
             'set -eu; '
             f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{BOOT_ID}"; '
             'test "$(readlink /proc/1/exe)" = /sbin/openrc-init; '
             'test "$(awk \'$2=="/" {print $3; exit}\' /proc/mounts)" = ext4; '
             f'test "$(sha256sum {target} | cut -c1-64)" = "{OLD_SHA}"; '
             f'test ! -e {backup}; test ! -e {staged}; '
             'test "$(stat -c %a /var/log/lynx/power.csv)" = 600; '
             'for s in lynx-health lynx-battery-reserve lynx-local-logs '
             'lynx-maintenance lynx-power-history; do '
             '/sbin/rc-service "$s" status >/dev/null; done; '
             'sample=$(cat /sys/bus/i2c/devices/7-0055/battery_snapshot); '
             'printf "%s\\n" "$sample" | grep -qx capacity_error=0; '
             'printf "%s\\n" "$sample" | grep -qx temperature_error=0; '
             'capacity=$(printf "%s\\n" "$sample" | sed -n "s/^capacity_percent=//p"); '
             'temp=$(printf "%s\\n" "$sample" | sed -n "s/^temperature_millidegrees_celsius=//p"); '
             'case "$capacity:$temp" in *[!0-9:]*|::*|*::*) exit 1;; esac; '
             'test "$capacity" -ge 50; test "$temp" -ge 10000; test "$temp" -lt 35000; '
             'printf LYNX_POWER_SYNC_UPDATE_READY')
        step('stage', f'cat > {staged}', payload=data)
        step('backup',
             'set -eu; '
             f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{BOOT_ID}"; '
             'install -d -m 0700 /root/lynx-rescue; '
             f'cp -p {target} {backup}; '
             f'test "$(sha256sum {backup} | cut -c1-64)" = "{OLD_SHA}"')
        backup_created = True
        step('install',
             'set -eu; '
             f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{BOOT_ID}"; '
             f'test "$(sha256sum {staged} | cut -c1-64)" = "{digest}"; '
             f'install -m 0755 {staged} {target}.new; '
             f'mv {target}.new {target}; '
             '/sbin/rc-service lynx-power-history restart; '
             '/sbin/rc-service lynx-power-history status; '
             'printf LYNX_POWER_HISTORY_SYNC_INSTALLED', timeout=35)
        proof = step('verify',
                     'set -eu; '
                     f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{BOOT_ID}"; '
                     f'test "$(sha256sum {target} | cut -c1-64)" = "{digest}"; '
                     f'test "$(sha256sum {backup} | cut -c1-64)" = "{OLD_SHA}"; '
                     f'/bin/sh {target} --once >/dev/null; '
                     'test "$(stat -c %a /var/log/lynx/power.csv)" = 600; '
                     '/sbin/rc-service lynx-power-history status; '
                     '/sbin/rc-service lynx-health status; '
                     'printf LYNX_POWER_HISTORY_FSYNC_VERIFIED', timeout=25)
        if 'LYNX_POWER_HISTORY_FSYNC_VERIFIED' not in proof:
            raise RuntimeError('Fsync proof absent')
        report['state'] = 'v47-power-history-fsync-installed-and-running'
    except Exception as exc:
        report.update(state='failed-or-incomplete', error=str(exc))
        if backup_created:
            try:
                step('restore_if_needed',
                     'set -eu; '
                     f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{BOOT_ID}"; '
                     f'test "$(sha256sum {backup} | cut -c1-64)" = "{OLD_SHA}"; '
                     f'cp -p {backup} {target}.restore; mv {target}.restore {target}; '
                     '/sbin/rc-service lynx-power-history restart; '
                     '/sbin/rc-service lynx-power-history status', timeout=35)
                report['old_service_restored'] = True
            except Exception as fallback:
                report['rollback_error'] = str(fallback)
    report['finished_ns'] = time.time_ns()
    result = out / 'result.json'
    result.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'state': report['state'], 'result': str(result)}))
    if report['state'] != 'v47-power-history-fsync-installed-and-running':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
