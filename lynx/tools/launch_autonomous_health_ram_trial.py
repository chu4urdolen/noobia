"""Fresh-V19, unplugged, RAM-only validation of the autonomous health stage.

Use --prepare first. --run needs the *fresh boot's* pinned V19 contact receipt
and current physical confirmation of no USB cable. No flash, slot or storage
write is possible through this tool. On failure, the stage's independent timer
requests power-off; this launcher never switches slots or reboots to Android.
"""
import argparse
import hashlib
import io
import json
import os
import subprocess
import tarfile
import time
from pathlib import Path

from lynx_wifi_v19_contact import PROOF, proof_valid, ssh_command

ROOT = Path(__file__).resolve().parent.parent
PORT = ROOT / 'linux-port'
ARCHIVE = PORT / 'artifacts/autonomous-health-inputs/inputs.tar.gz'
PREFLIGHT = PORT / 'autonomous-health-preflight.sh'
START = PORT / 'autonomous-health-start.sh'
REMOTE = '/run/lynx/health-inputs'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def validate_local():
    manifest = json.loads((ARCHIVE.parent / 'result.json').read_text())
    raw = ARCHIVE.read_bytes()
    if (manifest.get('state') != 'reviewed-inert-health-inputs' or
            not manifest.get('roundtrip_verified') or
            sha(raw) != manifest.get('archive_sha256')):
        raise ValueError('Health input archive differs from reviewed manifest')
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:gz') as tar:
        members = tar.getmembers()
        if any(not m.isfile() or m.name.startswith('/') or '..' in Path(m.name).parts for m in members):
            raise ValueError('Unsafe archive member')
        names = {m.name for m in members}
    for name in ('manifest.json', 'modules/nvmem_mtk-devinfo.ko',
                 'modules/soc_temp_lvts.ko', 'modules/mediatek-cpufreq-hw.ko',
                 'modules/lynx-gauge-sample.ko', 'modules/lynx-battery-monitor.ko'):
        if name not in names:
            raise ValueError('Missing health input: ' + name)
    scripts = {}
    for path in (PREFLIGHT, START):
        raw_script = path.read_bytes()
        check = subprocess.run(['sh', '-n'], input=raw_script, capture_output=True)
        if check.returncode:
            raise ValueError('Shell syntax failed: ' + path.name)
        scripts[path.name] = {'sha256': sha(raw_script), 'bytes': len(raw_script)}
    checks = {
        'autonomous-health-preflight.sh': PORT / 'artifacts/autonomous-health-preflight-check-1792264353611654369/result.json',
        'autonomous-health-start.sh': PORT / 'artifacts/autonomous-health-start-check-1792278260648743380/result.json',
    }
    for name, path in checks.items():
        checked = json.loads(path.read_text())
        if not checked.get('passed') or checked.get('source_sha256') != scripts[name]['sha256']:
            raise ValueError('Offline fixture failed: ' + str(path))
    v23 = json.loads((PORT / 'artifacts/health-stage-v23-offline/build-result.json').read_text())
    v25d = json.loads((PORT / 'artifacts/selfboot-health-v25d-offline/build-result.json').read_text())
    if (v23.get('scripts', {}).get('autonomous-health-preflight.sh') !=
            scripts['autonomous-health-preflight.sh']['sha256'] or
            v25d.get('script_sha256', {}).get('usr/libexec/lynx/autonomous-health-start.sh') !=
            scripts['autonomous-health-start.sh']['sha256']):
        raise ValueError('RAM trial scripts differ from reviewed packaged payloads')
    return {'archive_sha256': sha(raw), 'archive_bytes': len(raw),
            'scripts': scripts, 'offline_checks': [str(p) for p in checks.values()]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--prepare', action='store_true')
    mode.add_argument('--run', action='store_true')
    parser.add_argument('--contact-receipt', type=Path)
    parser.add_argument('--usb-unplugged-confirmed', action='store_true')
    args = parser.parse_args()
    local = validate_local()
    if args.prepare:
        print(json.dumps({'state': 'offline-ready-for-fresh-v19-ram-trial',
                          'phone_contacted': False, 'flash_performed': False,
                          'requires_fresh_pinned_v19_contact_receipt': True,
                          'requires_current_usb_unplugged_confirmation': True,
                          **local}))
        return
    if args.contact_receipt is None or not args.usb_unplugged_confirmed:
        parser.error('--run requires --contact-receipt and --usb-unplugged-confirmed')
    contact = json.loads(args.contact_receipt.read_text())
    if not (contact.get('native_ssh_verified') and contact.get('state') == 'native-ssh-available'
            and contact.get('fallback_cancel_ack_exit_code') == 0):
        raise ValueError('Fresh pinned V19 contact receipt not ready')
    ip = contact['phone_ip']
    os.umask(0o077)
    out = ROOT / 'logs' / ('autonomous-health-ram-trial-' + str(time.time_ns()))
    out.mkdir(mode=0o700)
    report = {'state': 'starting', 'started_ns': time.time_ns(),
              'contact_receipt': str(args.contact_receipt.resolve()),
              'phone_ip': ip, 'usb_unplugged_confirmed': True,
              'partition_writes': False, 'flash_performed': False,
              'operations': [], 'local': local}
    identity_verified = False

    def save():
        temporary = out / 'result.tmp'
        temporary.write_text(json.dumps(report, indent=2) + '\n')
        temporary.replace(out / 'result.json')

    def run(name, command, *, data=None, timeout=12):
        op = {'name': name, 'started_ns': time.time_ns(), 'command': command}
        report['operations'].append(op)
        save()
        with (out / (name + '.stdout')).open('wb') as stdout, \
                (out / (name + '.stderr')).open('wb') as stderr:
            try:
                child = subprocess.run(ssh_command(ip, command), input=data,
                                       stdout=stdout, stderr=stderr, timeout=timeout)
                op['exit_code'] = child.returncode
            except subprocess.TimeoutExpired:
                op.update(exit_code=None, timed_out=True)
        raw = (out / (name + '.stdout')).read_bytes()
        op.update(finished_ns=time.time_ns(), stdout_bytes=len(raw),
                  stdout_sha256=sha(raw))
        save()
        return raw, op['exit_code']

    try:
        proof, rc = run('identity', PROOF)
        if not proof_valid(proof.decode(errors='replace'), rc):
            raise ValueError('Pinned native V19 identity differs')
        identity_verified = True
        # Refuse a resumed or host-assisted session before writing even RAM
        # scripts. The new boot must still be within its supervised window.
        precheck = '''set -e
[ -r /run/lynx/host-confirmed ]
for name in nvmem_mtk_devinfo soc_temp_lvts oplus_omrg mediatek_cpufreq_hw lynx_battery_monitor; do
    [ ! -d "/sys/module/$name" ]
done
[ ! -e /run/lynx/thermal-watch.pid ]
[ ! -e /run/lynx/health-bootstrap ]
now=$(cut -d. -f1 /proc/uptime)
start=$(cat /run/lynx/network-timing-start)
case "$now:$start" in *[!0-9:]*) exit 1;; esac
[ "$now" -ge "$start" ] && [ "$((now-start))" -lt 240 ]
supplies=0
for p in /sys/class/power_supply/*; do
    [ -r "$p/online" ] || continue
    [ "$(cat "$p/online")" = 0 ]
    supplies=$((supplies+1))
done
[ "$supplies" -ge 1 ]
echo FRESH_UNPLUGGED_V19_RAM_TRIAL_READY'''
        pre, rc = run('fresh-boot-precheck', precheck)
        if rc != 0 or b'FRESH_UNPLUGGED_V19_RAM_TRIAL_READY' not in pre:
            raise ValueError('Fresh boot, stock module, timing or unplugged precheck refused')
        remote_scripts = '/usr/libexec/lynx'
        _, rc = run('prepare-ram-dir', 'mkdir -p ' + remote_scripts + ' && test ! -e ' + REMOTE)
        if rc != 0:
            raise ValueError('RAM script directory refused')
        for path in (PREFLIGHT, START):
            target = remote_scripts + '/' + path.name
            _, rc = run('upload-' + path.stem,
                        'test ! -e ' + target + ' && cat > ' + target,
                        data=path.read_bytes())
            if rc != 0:
                raise ValueError('RAM script upload failed: ' + path.name)
        _, rc = run('upload-health-inputs',
                    'test ! -e /run/lynx/health-inputs.tar.gz && cat > /run/lynx/health-inputs.tar.gz',
                    data=ARCHIVE.read_bytes())
        if rc != 0:
            raise ValueError('RAM input upload failed')
        checks = '; '.join(f'echo "{info["sha256"]}  {remote_scripts}/{name}" | /bin/busybox sha256sum -c -'
                           for name, info in local['scripts'].items())
        command = ('set -e; ' + checks + '; echo "' + local['archive_sha256'] +
                   '  /run/lynx/health-inputs.tar.gz" | /bin/busybox sha256sum -c -; '
                   'mkdir ' + REMOTE + '; /bin/busybox tar -xzf /run/lynx/health-inputs.tar.gz -C ' + REMOTE)
        _, rc = run('verify-extract', command, timeout=20)
        if rc != 0:
            raise ValueError('RAM health archive verification or extraction failed')
        _, rc = run('hardware-preflight', '/bin/busybox sh ' + remote_scripts +
                    '/autonomous-health-preflight.sh --check ' + REMOTE, timeout=20)
        if rc != 0:
            raise ValueError('Exact handset preflight refused before module insertion')
        report['state'] = 'running-on-phone-health-stage'
        save()
        _, rc = run('health-stage', '/bin/busybox sh ' + remote_scripts +
                    '/autonomous-health-start.sh --run ' + REMOTE, timeout=195)
        if rc != 0:
            raise ValueError('Health stage failed or timed out; independent phone power-off timer remains armed')
        health, rc = run('health-postcheck',
                         '/bin/busybox sh /run/lynx/lynx-health-supervisor.sh --once; '
                         'cat /run/lynx/battery-last; cat /proc/uptime', timeout=12)
        if rc != 0 or b'LYNX_HEALTH_OK' not in health:
            raise ValueError('Live health postcheck failed')
        report['state'] = 'phone-ram-health-stage-verified'
    except Exception as exc:
        report['state'] = 'failed-or-refused'
        report['error'] = str(exc)
        if identity_verified:
            # The V19 acknowledgement cancelled its automatic Fastboot timer.
            # A failed fresh trial must not leave an unmonitored Linux boot
            # running. Preserve an existing healthy session if invoked in error.
            try:
                state, _ = run('safety-state',
                               'if test -r /run/lynx/health-supervisor/pid && '
                               'kill -0 "$(cat /run/lynx/health-supervisor/pid)" 2>/dev/null; '
                               'then echo PROTECTED; else echo UNPROTECTED; fi')
                if b'UNPROTECTED' in state:
                    _, shutdown_rc = run('safe-poweroff-request',
                                         '/bin/busybox poweroff -f', timeout=6)
                    report['safe_poweroff_requested'] = True
                    report['safe_poweroff_ssh_exit_code'] = shutdown_rc
            except Exception as safety_exc:
                report['safety_followup_error'] = str(safety_exc)
        raise
    finally:
        report['finished_ns'] = time.time_ns()
        save()
        print(json.dumps({'state': report['state'], 'result': str(out / 'result.json')}))


if __name__ == '__main__':
    main()
