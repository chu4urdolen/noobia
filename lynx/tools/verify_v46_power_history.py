"""Read-only proof that Lynx's power historian sampled on its own timer."""

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time

from lynx_wifi_v19_contact import ssh_command


ROOT = Path(__file__).resolve().parent.parent
BOOT_ID = 'f6230cac-8d41-48da-bf28-2700e9ff56f1'
IP = '192.168.100.8'
SOURCES = {'script': (ROOT / 'linux-port/lynx-power-history.sh',
                      '/usr/libexec/lynx-power-history.sh'),
           'service': (ROOT / 'linux-port/openrc-lynx-power-history',
                       '/etc/init.d/lynx-power-history')}


def main():
    os.umask(0o077)
    out = ROOT / 'logs' / f'v46-power-history-verify-{time.time_ns()}'
    out.mkdir(mode=0o700)
    hashes = {name: hashlib.sha256(path.read_bytes()).hexdigest()
              for name, (path, _) in SOURCES.items()}
    command = (
        'set -eu; '
        f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{BOOT_ID}"; '
        f'test "$(sha256sum {SOURCES["script"][1]} | cut -c1-64)" = "{hashes["script"]}"; '
        f'test "$(sha256sum {SOURCES["service"][1]} | cut -c1-64)" = "{hashes["service"]}"; '
        'test "$(readlink -f /etc/runlevels/default/lynx-power-history)" = /etc/init.d/lynx-power-history; '
        'test "$(stat -c %a /var/log/lynx/power.csv)" = 600; '
        'test "$(stat -c %a /var/log/lynx)" = 700; '
        '/sbin/rc-service lynx-power-history status >/dev/null; '
        '/sbin/rc-service lynx-health status >/dev/null; '
        '/sbin/rc-service lynx-battery-reserve status >/dev/null; '
        'cat /var/log/lynx/power.csv'
    )
    argv = ssh_command(IP, command)
    argv[-2:-2] = ['-p', '2222']
    run = subprocess.run(argv, capture_output=True, timeout=20)
    (out / 'stdout').write_bytes(run.stdout)
    (out / 'stderr').write_bytes(run.stderr)
    rows = []
    if run.returncode == 0:
        lines = run.stdout.decode(errors='replace').splitlines()
        if lines and lines[0] == (
                'boot_id,uptime_s,epoch_s,capacity_percent,current_ma,'
                'battery_temp_mC,pack_voltage_mV'):
            for line in lines[1:]:
                fields = line.split(',')
                if len(fields) != 7 or fields[0] != BOOT_ID or not all(
                        re.fullmatch(r'-?\d+', item) for item in fields[1:]):
                    break
                values = [int(item) for item in fields[1:]]
                if not (0 <= values[2] <= 100 and -32768 <= values[3] <= 32767 and
                        10000 <= values[4] <= 60000 and 5000 <= values[5] <= 10000):
                    break
                rows.append(values)
    distinct_uptimes = sorted({row[0] for row in rows})
    passed = (len(rows) >= 3 and
              len(distinct_uptimes) >= 2 and
              distinct_uptimes[-1] - distinct_uptimes[0] >= 50)
    state = ('v46-power-history-autonomous-sampling-verified' if passed
             else 'failed-or-incomplete')
    result = out / 'result.json'
    result.write_text(json.dumps({'state': state, 'boot_id': BOOT_ID,
                                  'phone_ip': IP, 'sha256': hashes,
                                  'rows_verified': len(rows),
                                  'distinct_sample_uptimes': distinct_uptimes,
                                  'exit_code': run.returncode,
                                  'phone_writes': False}, indent=2) + '\n')
    print(json.dumps({'state': state, 'result': str(result)}))
    if not passed:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
