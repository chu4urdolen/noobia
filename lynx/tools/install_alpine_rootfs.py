"""Trial the VM-proven ARM64 rootfs in Lynx's RAM, preserving the native session."""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

from alpine_rootfs import ROOT, ARCHIVE_SHA256, PROBE, read_rootfs
from fetch_alpine_rootfs import VERSION

DESTINATION = '/run/lynx/alpine-' + VERSION
ARCHIVE = DESTINATION + '.tar.gz'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--session', type=Path)
    parser.add_argument('--rootfs-receipt', type=Path)
    parser.add_argument('--vm-receipt', type=Path)
    parser.add_argument('--install', action='store_true')
    args = parser.parse_args()
    if not args.install:
        print('Use --install with verified session, rootfs and VM receipts. No phone contacted.')
        return
    if any(value is None for value in [args.session, args.rootfs_receipt, args.vm_receipt]):
        parser.error('--session, --rootfs-receipt and --vm-receipt are required')
    _, inventory = read_rootfs(args.rootfs_receipt)
    vm = json.loads(args.vm_receipt.read_text())
    console = args.vm_receipt.with_name('console.log').read_bytes()
    if not (vm.get('passed') and vm['inventory']['archive_sha256'] == ARCHIVE_SHA256
            and vm['kernel_sha256'] == 'cbc9f5dc54b5198ddd1e82d5d7bde96f43cbb383a663726ddd68919b0639d3af'
            and hashlib.sha256(console).hexdigest() == vm['console_sha256']
            and b'LYNX_ALPINE_USERSPACE_PASS' in console):
        raise ValueError('Matching successful stock-kernel VM evidence required')
    os.umask(0o077)
    out = ROOT / 'logs' / ('alpine-rootfs-trial-' + str(time.time_ns()))
    out.mkdir(mode=0o700)
    (out / 'probe.sh').write_text(PROBE)
    report = {'state': 'starting', 'started_ns': time.time_ns(), 'operations': [],
              'session': str(args.session.resolve()), 'rootfs_inventory': inventory,
              'vm_receipt': str(args.vm_receipt.resolve()), 'destination': DESTINATION,
              'probe_sha256': hashlib.sha256(PROBE.encode()).hexdigest(), 'flash_performed': False,
              'new_mounts': False, 'new_services': False, 'unconditional_shutdown': False}

    def save():
        temporary = out / 'result.tmp'
        temporary.write_text(json.dumps(report, indent=2) + '\n')
        temporary.replace(out / 'result.json')

    def run(name, arguments, timeout=40):
        operation = {'name': name, 'started_ns': time.time_ns(), 'argv': arguments}
        report['operations'].append(operation); save()
        with (out / (name + '.stdout')).open('wb') as stdout, (out / (name + '.stderr')).open('wb') as stderr:
            try:
                process = subprocess.run(arguments, stdout=stdout, stderr=stderr, timeout=timeout, cwd=ROOT)
                operation['exit_code'] = process.returncode
            except subprocess.TimeoutExpired:
                operation.update(exit_code=None, timed_out=True)
        data = (out / (name + '.stdout')).read_bytes()
        operation.update(finished_ns=time.time_ns(), stdout_sha256=hashlib.sha256(data).hexdigest())
        save()
        if operation['exit_code'] != 0:
            raise ValueError(name + ' failed; partial RAM state and raw captures retained')
        return json.loads(data)

    def live(name, command, payload=None, timeout=20):
        if any(ord(character) < 32 and character not in '\n\t' for character in command):
            raise ValueError('Unexpected control character in remote command')
        arguments = [sys.executable, str(ROOT / 'tools/lynx_live_command.py'), '--session', str(args.session),
                     '--name', 'alpine-' + name, '--command', command, '--timeout', str(timeout)]
        if payload:
            arguments.extend(['--stdin-file', str(payload)])
        result = run(name, arguments, timeout=timeout + 30)
        receipt_path = Path(result['result'])
        receipt = json.loads(receipt_path.read_text())
        operation = next(op for op in receipt['operations'] if op['name'] == 'command')
        data = receipt_path.with_name('command.stdout').read_bytes()
        if not receipt['native_identity_verified'] or hashlib.sha256(data).hexdigest() != operation['stdout_sha256']:
            raise ValueError('Child capture identity/hash mismatch')
        report['operations'][-1]['live_receipt'] = str(receipt_path); save()
        return data.decode()

    try:
        power = run('power-preflight', [sys.executable, str(ROOT / 'tools/configure_runtime_power.py'),
                    '--session', str(args.session), '--verify-only'], timeout=90)
        power_receipt = json.loads(Path(power['result']).read_text())
        if power['state'] != 'ready':
            raise ValueError('Working power setup required')
        boot_id = str(uuid.UUID(power_receipt['boot_id']))
        report['boot_id'] = boot_id
        guard = 'set -eu; test "$(cat /proc/sys/kernel/random/boot_id)" = ' + boot_id + '; '
        preflight = guard + """awk '$2=="/run" && ($3=="tmpfs" || $3=="ramfs") {ok=1} END {exit !ok}' /proc/mounts
available=$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo)
test "$available" -ge 131072
temperature=$(sed -n 's/^temperature_millidegrees_celsius=//p' /run/lynx/battery-last)
capacity=$(sed -n 's/^capacity_percent=//p' /run/lynx/battery-last)
test "$temperature" -gt 0; test "$temperature" -lt 35000
test "$capacity" -ge 20
test "$(cat /sys/class/power_supply/11e01000.i2c:mt6375@34:chg/online)" = 0
""" + 'test ! -e ' + DESTINATION + '; test ! -e ' + ARCHIVE + '; echo LYNX_ALPINE_PREFLIGHT_PASS; cat /run/lynx/battery-last'
        live('preflight', preflight)
        upload = guard + 'test ! -e ' + ARCHIVE + '; cat > ' + ARCHIVE + '.partial; echo "' + ARCHIVE_SHA256 + '  ' + ARCHIVE + '.partial" | sha256sum -c -; mv ' + ARCHIVE + '.partial ' + ARCHIVE
        live('upload', upload, Path(inventory['archive']), timeout=45)
        unpack = guard + 'test ! -e ' + DESTINATION + '; mkdir ' + DESTINATION + '; /bin/busybox tar -xzf ' + ARCHIVE + ' -C ' + DESTINATION + '; test "$(cat ' + DESTINATION + '/etc/alpine-release)" = ' + VERSION + '; echo LYNX_ALPINE_UNPACKED'
        live('unpack', unpack)
        proof = live('probe', guard + '/bin/busybox chroot ' + DESTINATION + ' /bin/sh -s', out / 'probe.sh')
        if 'LYNX_ALPINE_USERSPACE_PASS\n' not in proof or '5.10.149-android12-9-o-g311738fbb5a8\n' not in proof:
            raise ValueError('Native rootfs proof incomplete')
        power = run('power-after', [sys.executable, str(ROOT / 'tools/configure_runtime_power.py'),
                    '--session', str(args.session), '--verify-only'], timeout=90)
        after = json.loads(Path(power['result']).read_text())
        if power['state'] != 'ready' or after['boot_id'] != boot_id:
            raise ValueError('Original runtime/boot not verified after trial')
        report.update(state='native-userspace-verified', native_rootfs_verified=True,
                      original_runtime_verified=True, rootfs_left_in_ram=True)
    except Exception as error:
        report.update(state='failed', error=str(error))
    report['finished_ns'] = time.time_ns(); save()
    print(json.dumps({'state': report['state'], 'result': str(out / 'result.json')}))
    if report['state'] != 'native-userspace-verified':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
