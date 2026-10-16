"""Install or verify the hardware-tested RAM power setup over pinned SSH.

No contact without --apply/--verify-only. Never flashes, reboots, stops an
existing watcher, clears saved state, or changes charging/suspend policy.
"""
import argparse
import hashlib
import json
import os
import subprocess
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCES = {
    'wfi-fallback.sh': '866c9d2429a10d6cb4294136622668a840d761cfba65037bd95e3cabf290fab0',
    'thermal-cooling-watch.sh': '5310290b6a8e981e2250910fb5b4b54428a1faa6b1f6177e36f5be2aade1233b',
}
TEMPLATE = r'''#!/bin/sh
set -eu
mode=MODE_VALUE
require_process() {
    pid=$(cat "$1")
    case "$pid" in ''|*[!0-9]*) return 1;; esac
    kill -0 "$pid"
    tr '\000' '\n' < "/proc/$pid/cmdline" | grep -Fx "$2" > /dev/null
}
verify_wfi() {
    [ -s /run/lynx/wfi-fallback/original-flags ]
    expected=0 saved=0 cpus=0
    for cpu in /sys/devices/system/cpu/cpu[0-9]*; do
        [ "$(cat "$cpu/cpuidle/state0/name")" = WFI ]
        [ "$(cat "$cpu/cpuidle/state0/disable")" = 0 ]
        cpus=$((cpus + 1))
        for state in "$cpu"/cpuidle/state*; do
            [ -d "$state" ] || continue
            case "$state" in */state0) continue;; esac
            [ "$(cat "$state/disable")" = 1 ]
            [ "$(grep -Fc "$state/disable " /run/lynx/wfi-fallback/original-flags)" = 1 ]
            expected=$((expected + 1))
        done
    done
    [ "$cpus" = 8 ]
    while read -r path original; do
        case "$path" in /sys/devices/system/cpu/cpu[0-9]*/cpuidle/state[1-9]*/disable) ;; *) return 1;; esac
        case "$original" in 0|1) ;; *) return 1;; esac
        [ "$(cat "$path")" = 1 ]
        saved=$((saved + 1))
    done < /run/lynx/wfi-fallback/original-flags
    [ "$saved" = "$expected" ]
    echo WFI_FALLBACK_VERIFIED
}
echo RUNTIME_POWER_BOOT_ID
cat /proc/sys/kernel/random/boot_id
require_process /run/lynx/thermal-watch.pid /run/lynx/thermal-watch.sh
require_process /run/lynx/battery-watch.pid /run/lynx/battery-watch.sh
# Refuse stale/missing or invalid battery observations before new setup.
now=$(cut -d. -f1 /proc/uptime)
sample=$(sed -n 's/^sample_uptime_seconds=//p' /run/lynx/battery-last)
sample=${sample%%.*}
case "$sample" in ''|*[!0-9]*) exit 1;; esac
[ "$now" -ge "$sample" ] && [ "$((now - sample))" -le 15 ]
for field in temperature_error voltage_error current_error capacity_error; do
    grep -Fx "$field=0" /run/lynx/battery-last > /dev/null
done
if [ "$mode" = apply ]; then
    mkdir /run/lynx/runtime-power-setup.lock
    trap 'rmdir /run/lynx/runtime-power-setup.lock' EXIT
fi
SOURCE_INSTALLATIONS
if [ -d /run/lynx/wfi-fallback ]; then
    verify_wfi
elif [ "$mode" = apply ]; then
    sh /run/lynx/wfi-fallback.sh --apply
    verify_wfi
else
    echo WFI_FALLBACK_MISSING >&2
    exit 1
fi
if [ -d /run/lynx/thermal-cooling-watch ]; then
    test -f /run/lynx/thermal-cooling-watch/ready
    require_process /run/lynx/thermal-cooling-watch/pid /run/lynx/thermal-cooling-watch.sh
    echo SOFT_THROTTLE_EXISTING_PROCESS_VERIFIED
elif [ "$mode" = apply ]; then
    nohup sh /run/lynx/thermal-cooling-watch.sh --run > /run/lynx/thermal-cooling-watch.log 2>&1 < /dev/null &
    launched=$!
    sleep 1
    [ "$(cat /run/lynx/thermal-cooling-watch/pid)" = "$launched" ]
    test -f /run/lynx/thermal-cooling-watch/ready
    require_process /run/lynx/thermal-cooling-watch/pid /run/lynx/thermal-cooling-watch.sh
    echo SOFT_THROTTLE_STARTED
else
    echo SOFT_THROTTLE_MISSING >&2
    exit 1
fi
echo WATCHER_PIDS
cat /run/lynx/thermal-watch.pid /run/lynx/battery-watch.pid /run/lynx/thermal-cooling-watch/pid
echo BATTERY
cat /run/lynx/battery-last
echo WIFI_POWER_SAVE
/usr/sbin/iw dev wlan0 get power_save
echo SOFT_THROTTLE_LOG
tail -n 2 /run/lynx/thermal-cooling-watch.log
echo RUNTIME_POWER_READY
'''


def build_payload(mode):
    if mode not in ('apply', 'check'):
        raise ValueError('Invalid setup mode')
    installations = []
    for name, digest in SOURCES.items():
        data = (ROOT / 'linux-port' / name).read_bytes()
        if hashlib.sha256(data).hexdigest() != digest:
            raise ValueError('Hardware-reviewed source changed: ' + name)
        marker = 'LYNX_SOURCE_' + digest
        text = data.decode()
        if marker in text:
            raise ValueError('Source delimiter collision')
        target = '/run/lynx/' + name
        installations.append(f'''if [ ! -e {target} ] && [ "$mode" = apply ]; then
    cat > {target}.setup-tmp <<'{marker}'
{text.rstrip()}
{marker}
    echo '{digest}  {target}.setup-tmp' | sha256sum -c -
    mv {target}.setup-tmp {target}
fi
echo '{digest}  {target}' | sha256sum -c -''')
    return TEMPLATE.replace('MODE_VALUE', mode).replace('SOURCE_INSTALLATIONS', '\n'.join(installations)).encode()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--session', type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--apply', action='store_true')
    mode.add_argument('--verify-only', action='store_true')
    args = parser.parse_args()
    if not (args.apply or args.verify_only):
        print('Use --session RECEIPT --apply after battery resume, or --verify-only. No phone contacted.')
        return
    if args.session is None:
        parser.error('--session is required')
    payload = build_payload('apply' if args.apply else 'check')
    session = json.loads(args.session.read_text())
    if not (session.get('native_identity_verified') and session.get('session_left_running')):
        raise ValueError('Verified continuous session required')
    from lynx_wifi_v19_contact import PROOF, proof_valid, ssh_command
    os.umask(0o077)
    out = ROOT / 'logs' / ('runtime-power-setup-' + str(time.time_ns()))
    out.mkdir(mode=0o700)
    (out / 'payload.sh').write_bytes(payload)
    report = {'state': 'starting', 'started_ns': time.time_ns(), 'session': str(args.session.resolve()),
              'mode': 'apply' if args.apply else 'check', 'operations': [], 'sources': SOURCES,
              'payload_sha256': hashlib.sha256(payload).hexdigest(), 'flash_performed': False,
              'unconditional_shutdown': False}

    def save():
        temporary = out / 'result.tmp'
        temporary.write_text(json.dumps(report, indent=2) + '\n')
        temporary.replace(out / 'result.json')

    def run(name, command, data=None):
        operation = {'name': name, 'started_ns': time.time_ns()}
        report['operations'].append(operation)
        save()
        with (out / (name + '.stdout')).open('wb') as stdout, (out / (name + '.stderr')).open('wb') as stderr:
            try:
                process = subprocess.run(ssh_command(session['phone_ip'], command), input=data,
                                         stdout=stdout, stderr=stderr, timeout=25)
                operation['exit_code'] = process.returncode
            except subprocess.TimeoutExpired:
                operation.update(exit_code=None, timed_out=True)
        raw = (out / (name + '.stdout')).read_bytes()
        operation.update(finished_ns=time.time_ns(), stdout_sha256=hashlib.sha256(raw).hexdigest())
        save()
        if operation['exit_code'] != 0:
            raise ValueError(name + ' failed; raw captures retained')
        return raw.decode()

    try:
        if not proof_valid(run('identity', PROOF), 0):
            raise ValueError('Native identity mismatch')
        raw = run('configure', 'sh -s', payload)
        if '\nRUNTIME_POWER_READY\n' not in raw:
            raise ValueError('Runtime readiness marker missing')
        boot_id = str(uuid.UUID(raw.split('RUNTIME_POWER_BOOT_ID\n', 1)[1].splitlines()[0]))
        after = run('identity-after', PROOF + "; printf 'RUNTIME_POWER_BOOT_ID\\n'; cat /proc/sys/kernel/random/boot_id")
        if not proof_valid(after, 0):
            raise ValueError('Native identity missing after setup')
        if after.split('RUNTIME_POWER_BOOT_ID\n', 1)[1].splitlines()[0] != boot_id:
            raise ValueError('Phone boot changed during setup')
        report.update(state='ready', native_identity_verified=True,
                      boot_id=boot_id)
    except Exception as error:
        report.update(state='failed', error=str(error))
    report['finished_ns'] = time.time_ns()
    save()
    print(json.dumps({'state': report['state'], 'result': str(out / 'result.json')}))
    if report['state'] != 'ready':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
