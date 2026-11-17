"""Install read-only power history on verified V46 Alpine without reboot."""

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time

from lynx_wifi_v19_contact import ssh_command


ROOT = Path(__file__).resolve().parent.parent
PORT = ROOT / 'linux-port'
SOURCES = {
    'script': (PORT / 'lynx-power-history.sh', '/usr/libexec/lynx-power-history.sh'),
    'service': (PORT / 'openrc-lynx-power-history', '/etc/init.d/lynx-power-history'),
}
BOOT_ID = 'f6230cac-8d41-48da-bf28-2700e9ff56f1'
IP = '192.168.100.8'


def main():
    for source, _ in SOURCES.values():
        subprocess.run(['/bin/sh', '-n', str(source)], check=True)
    payloads = {name: path.read_bytes() for name, (path, _) in SOURCES.items()}
    hashes = {name: hashlib.sha256(data).hexdigest() for name, data in payloads.items()}
    os.umask(0o077)
    out = ROOT / 'logs' / f'v46-power-history-install-{time.time_ns()}'
    out.mkdir(mode=0o700)
    report = {'state': 'starting', 'phone_ip': IP, 'boot_id': BOOT_ID,
              'sha256': hashes, 'boot_partition_writes': False,
              'steps': []}

    def step(name, command, payload=None, timeout=25):
        argv = ssh_command(IP, command)
        argv[-2:-2] = ['-p', '2222']
        run = subprocess.run(argv, input=payload, capture_output=True, timeout=timeout)
        (out / f'{name}.stdout').write_bytes(run.stdout)
        (out / f'{name}.stderr').write_bytes(run.stderr)
        report['steps'].append({'name': name, 'exit_code': run.returncode,
                                'stdout_sha256': hashlib.sha256(run.stdout).hexdigest()})
        if run.returncode:
            raise RuntimeError(f'{name} failed; see saved streams')
        return run.stdout.decode(errors='replace')

    try:
        preflight = step('preflight',
            'set -eu; '
            f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{BOOT_ID}"; '
            'test "$(readlink /proc/1/exe)" = /sbin/openrc-init; '
            'test "$(awk \'$2=="/" {print $3; exit}\' /proc/mounts)" = ext4; '
            'for s in lynx-health lynx-battery-reserve lynx-local-logs lynx-time-sync; do '
            '/sbin/rc-service "$s" status >/dev/null; done; '
            'sample=$(cat /sys/bus/i2c/devices/7-0055/battery_snapshot); '
            'printf "%s\\n" "$sample" | grep -qx capacity_error=0; '
            'printf "%s\\n" "$sample" | grep -qx temperature_error=0; '
            'capacity=$(printf "%s\\n" "$sample" | sed -n "s/^capacity_percent=//p"); '
            'temp=$(printf "%s\\n" "$sample" | sed -n "s/^temperature_millidegrees_celsius=//p"); '
            'case "$capacity:$temp" in *[!0-9:]*|::*|*::*) exit 1;; esac; '
            'test "$capacity" -ge 50; test "$temp" -ge 10000; test "$temp" -lt 35000; '
            'test "$(df -Pm / | awk \'NR==2 {print $4}\')" -ge 500; '
            'test ! -e /usr/libexec/lynx-power-history.sh; '
            'test ! -e /etc/init.d/lynx-power-history; '
            'test ! -e /etc/runlevels/default/lynx-power-history; '
            'printf "LYNX_POWER_HISTORY_READY capacity=%s temp_mC=%s\\n" "$capacity" "$temp"')
        if not re.fullmatch(r'LYNX_POWER_HISTORY_READY capacity=\d+ temp_mC=\d+\n', preflight):
            raise RuntimeError('Preflight marker absent')
        report['battery_preflight'] = preflight.strip()
        for name, (_, target) in SOURCES.items():
            step('stage_' + name, f'cat > /run/lynx/power-history.{name}.new',
                 payload=payloads[name])
            step('install_' + name,
                 'set -eu; '
                 f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{BOOT_ID}"; '
                 f'test "$(sha256sum /run/lynx/power-history.{name}.new | cut -c1-64)" = "{hashes[name]}"; '
                 f'install -m 0755 /run/lynx/power-history.{name}.new {target}; '
                 f'test "$(sha256sum {target} | cut -c1-64)" = "{hashes[name]}"')
        sample = step('first_sample',
                      '/bin/sh /usr/libexec/lynx-power-history.sh --once')
        if not re.fullmatch(r'[0-9a-f-]{36},\d+,\d+,\d+,-?\d+,\d+,\d+\n', sample):
            raise RuntimeError('Power-history sample format differs')
        step('enable',
             '/sbin/rc-update add lynx-power-history default && '
             '/sbin/rc-service lynx-power-history start && '
             '/sbin/rc-service lynx-power-history status', timeout=35)
        proof = step('verify',
                     'set -eu; '
                     f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{BOOT_ID}"; '
                     f'test "$(sha256sum /usr/libexec/lynx-power-history.sh | cut -c1-64)" = "{hashes["script"]}"; '
                     f'test "$(sha256sum /etc/init.d/lynx-power-history | cut -c1-64)" = "{hashes["service"]}"; '
                     'test "$(readlink -f /etc/runlevels/default/lynx-power-history)" = /etc/init.d/lynx-power-history; '
                     'test "$(stat -c %a /var/log/lynx/power.csv)" = 600; '
                     'test "$(stat -c %a /var/log/lynx)" = 700; '
                     'test "$(wc -l < /var/log/lynx/power.csv)" -ge 2; '
                     '/sbin/rc-service lynx-power-history status; '
                     '/sbin/rc-service lynx-health status; '
                     'printf LYNX_POWER_HISTORY_VERIFIED')
        if 'LYNX_POWER_HISTORY_VERIFIED' not in proof:
            raise RuntimeError('Verification marker absent')
        report['state'] = 'v46-power-history-installed-and-running'
    except Exception as exc:
        report.update(state='failed-or-incomplete', error=str(exc))
    report['finished_ns'] = time.time_ns()
    result = out / 'result.json'
    result.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'state': report['state'], 'result': str(result)}))
    if report['state'] != 'v46-power-history-installed-and-running':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
