#!/usr/bin/env python3
"""Install and verify Lynx's local, unprivileged console service."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

from lynx_wifi_v19_contact import ssh_command

ROOT = Path(__file__).resolve().parent.parent
BOOT = '6168cd6288679a321a4d8bc41c7d3dde64a49d3cfe855b8e44542f3307fd5a59'
DISPLAY = '96a5b979e92d9903829162fa8b12266c624d03e7bd84ffe39fde382f639c1a0a'
BOOTSTRAP = 'ff2dfc84c78121ac3f1b9411e9c216a42830ca02bb326555e36d43fb5c045265'


def remote(command, data=None, timeout=20):
    argv = ssh_command('192.168.100.107', command)
    argv[-2:-2] = ['-p', '2222']
    result = subprocess.run(argv, input=data, capture_output=True, timeout=timeout)
    return {'rc': result.returncode,
            'stdout': result.stdout.decode(errors='replace'),
            'stderr': result.stderr.decode(errors='replace')}


def step(name, command, data=None, timeout=20):
    result = remote(command, data, timeout)
    report['steps'].append({'name': name, **result})
    if result['rc']:
        raise RuntimeError(f'{name}: {result["stderr"] or result["stdout"]}')
    return result['stdout'].strip()


report = {'started_ns': time.time_ns(), 'steps': []}
receipt = ROOT / 'logs' / f'v50-console-service-{report["started_ns"]}' / 'result.json'
receipt.parent.mkdir(parents=True, exist_ok=True)

try:
    daemon = (ROOT / 'tools/lynx_console.py').read_bytes()
    init = (ROOT / 'linux-port/openrc-lynx-console').read_bytes()
    daemon_sha = hashlib.sha256(daemon).hexdigest()
    init_sha = hashlib.sha256(init).hexdigest()
    subprocess.run([sys.executable, '-m', 'py_compile', str(ROOT / 'tools/lynx_console.py')],
                   check=True)
    subprocess.run(['/bin/sh', '-n', str(ROOT / 'linux-port/openrc-lynx-console')],
                   check=True)
    status = step('preflight', 'set -eu; sha256sum /dev/sdc39 '
                  '/usr/local/bin/lynx-portrait-display '
                  '/usr/local/bin/lynx-display-bootstrap; '
                  '/usr/local/bin/lynx-status --assert-ready; '
                  'rc-service lynx-display status')
    lines = status.splitlines()
    if [line.split()[0] for line in lines[:3]] != [BOOT, DISPLAY, BOOTSTRAP]:
        raise RuntimeError('boot or display pin changed')
    health = json.loads(next(line for line in lines if line.startswith('{')))
    battery = health['battery']
    if (health['issues'] or battery['capacity_percent'] < 25 or
            battery['temperature_mC'] >= 35000 or
            health['thermal']['max_mC'] >= 45000):
        raise RuntimeError('health, battery, or thermal preflight failed')
    report['boot_id'] = health['boot_id']
    report['battery_percent'] = battery['capacity_percent']
    step('stage_daemon', 'set -eu; cat > /usr/local/bin/lynx-console.new; '
         f'test "$(sha256sum /usr/local/bin/lynx-console.new | cut -c1-64)" = {daemon_sha}; '
         'python3 -m py_compile /usr/local/bin/lynx-console.new', daemon)
    step('stage_init', 'set -eu; cat > /etc/init.d/lynx-console.new; '
         f'test "$(sha256sum /etc/init.d/lynx-console.new | cut -c1-64)" = {init_sha}; '
         'sh -n /etc/init.d/lynx-console.new', init)
    step('install', 'set -eu; '
         'if rc-service lynx-console status >/dev/null 2>&1; then '
         'echo "console already running" >&2; exit 1; fi; '
         'if test -e /usr/local/bin/lynx-console; then '
         'existing=$(sha256sum /usr/local/bin/lynx-console | cut -c1-64); '
         f'case "$existing" in {daemon_sha}|'
         '5d42ecb97de1f2212624ef99f9b8592a8c0fcb220f74b51a73e017cfdfc4c133) ;; '
         '*) exit 1;; esac; fi; '
         'if test -e /etc/init.d/lynx-console; then '
         'existing=$(sha256sum /etc/init.d/lynx-console | cut -c1-64); '
         f'case "$existing" in {init_sha}|'
         '414333168ddede1fc35ccd91bb48b1a35618305ce76ec4ab1884aff24b9ee479) ;; '
         '*) exit 1;; esac; fi; '
         'if ! id -u lynx-console >/dev/null 2>&1; then '
         'adduser -S -D -H -h /var/lib/lynx-console -s /sbin/nologin lynx-console; fi; '
         'test "$(id -u lynx-console)" != 0; '
         'chmod 755 /usr/local/bin/lynx-console.new /etc/init.d/lynx-console.new; '
         'mv /usr/local/bin/lynx-console.new /usr/local/bin/lynx-console; '
         'mv /etc/init.d/lynx-console.new /etc/init.d/lynx-console; '
         'rc-service lynx-console start; rc-service lynx-console status', timeout=35)
    step('identity', 'set -eu; uid=$(id -u lynx-console); '
         'pid=$(cat /run/lynx-console/daemon.pid); '
         'test "$(sed -n "s/^Uid:[[:space:]]*\\([0-9]*\\).*/\\1/p" /proc/$pid/status)" = "$uid"; '
         'test "$(stat -c %u /run/lynx-console/control.sock)" = "$uid"; '
         'echo uid=$uid daemon_pid=$pid; '
         'python3 /usr/local/bin/lynx-console --send pwd; '
         'python3 /usr/local/bin/lynx-console --send "echo CONSOLE_STDOUT_OK"; '
         'python3 /usr/local/bin/lynx-console --send "echo warning: CONSOLE_STDWARN_OK >&2"; '
         'python3 /usr/local/bin/lynx-console --send "echo CONSOLE_STDERR_OK >&2"; '
         'sleep 1; grep -Fq "O|CONSOLE_STDOUT_OK" /run/lynx-console/snapshot.txt; '
         'grep -Fq "W|warning: CONSOLE_STDWARN_OK" /run/lynx-console/snapshot.txt; '
         'grep -Fq "E|CONSOLE_STDERR_OK" /run/lynx-console/snapshot.txt; '
         'echo streams=verified', timeout=20)
    step('enable', 'set -eu; rc-update add lynx-console default; '
         'rc-service lynx-console status; /usr/local/bin/lynx-status --assert-ready >/dev/null')
    report['result'] = 'installed-running-enabled'
except Exception as exc:
    report['result'] = 'failed-or-incomplete'
    report['error'] = str(exc)
finally:
    report['finished_ns'] = time.time_ns()
    receipt.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'result': report['result'], 'receipt': str(receipt)}))
if report['result'] != 'installed-running-enabled':
    sys.exit(1)
