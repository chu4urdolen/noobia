"""Run the VM-proven optional RAM stage after native SSH and power setup."""
import argparse
import json
import os
import shlex
import subprocess
import sys
import time
import uuid
from pathlib import Path

from alpine_rootfs import ROOT
from prepare_alpine_runtime_stage import prepare, pack_inputs, sha


def load_stage(path):
    report = json.loads(path.read_text())
    console = path.with_name('console.log').read_bytes()
    if not (report.get('vm_passed') and all(report['checks'].values())
            and report['kernel_sha256'] == 'cbc9f5dc54b5198ddd1e82d5d7bde96f43cbb383a663726ddd68919b0639d3af'
            and sha(console) == report['console_sha256']):
        raise ValueError('Successful matching cold-stage VM evidence required')
    members, inventory = prepare(Path(report['rootfs_receipt']), Path(report['package_receipt']))
    if {name: {'bytes': len(data), 'sha256': sha(data)} for name, data in members.items()} != report['inputs']:
        raise ValueError('Current stage source/inputs differ from VM-tested bytes')
    return members, inventory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--session', type=Path)
    parser.add_argument('--stage-receipt', type=Path)
    action = parser.add_mutually_exclusive_group()
    action.add_argument('--install', action='store_true')
    action.add_argument('--verify-existing', action='store_true')
    action.add_argument('--isolated-replay', action='store_true')
    args = parser.parse_args()
    if not any([args.install, args.verify_existing, args.isolated_replay]):
        print('Use --session RECEIPT --stage-receipt RECEIPT with --install, --verify-existing or --isolated-replay. No phone contacted.')
        return
    if args.session is None or args.stage_receipt is None:
        parser.error('--session and --stage-receipt required')
    # Child tools run from ROOT; resolve user paths before changing their cwd.
    args.session = args.session.resolve(strict=True)
    args.stage_receipt = args.stage_receipt.resolve(strict=True)
    members, inventory = load_stage(args.stage_receipt)
    replay = None
    if args.isolated_replay:
        stage_vm = json.loads(args.stage_receipt.read_text())
        replay = (ROOT / 'linux-port/alpine-isolated-replay.sh').read_bytes()
        if not (stage_vm.get('isolated_replay_requested') and stage_vm['checks'].get('isolated_cold_replay')
                and stage_vm['checks'].get('isolated_parent_preserved') and sha(replay) == stage_vm.get('replay_sha256')):
            raise ValueError('Matching successful isolated-replay VM evidence required')
    os.umask(0o077)
    label = 'alpine-isolated-replay-' if args.isolated_replay else ('alpine-rootfs-trial-' if args.install else 'alpine-runtime-verify-')
    out = ROOT / 'logs' / (label + str(time.time_ns()))
    out.mkdir(mode=0o700)
    report = {'state': 'starting', 'started_ns': time.time_ns(), 'operations': [],
              'session': str(args.session.resolve()), 'stage_receipt': str(args.stage_receipt.resolve()),
              'rootfs_inventory': inventory, 'destination': '/run/lynx/alpine-3.24.2',
              'mode': 'isolated-replay' if args.isolated_replay else ('install' if args.install else 'verify-existing'), 'flash_performed': False,
              'new_services': False, 'unconditional_shutdown': False}
    def save():
        temporary = out / 'result.tmp'
        temporary.write_text(json.dumps(report, indent=2) + '\n')
        temporary.replace(out / 'result.json')
    def run(name, arguments, timeout=90):
        op = {'name': name, 'started_ns': time.time_ns(), 'argv': list(map(str, arguments))}
        report['operations'].append(op); save()
        with (out / (name + '.stdout')).open('wb') as stdout, (out / (name + '.stderr')).open('wb') as stderr:
            try:
                process = subprocess.run(list(map(str, arguments)), cwd=ROOT, stdout=stdout, stderr=stderr, timeout=timeout)
                op['exit_code'] = process.returncode
            except subprocess.TimeoutExpired:
                op.update(exit_code=None, timed_out=True)
        raw = (out / (name + '.stdout')).read_bytes()
        op.update(finished_ns=time.time_ns(), stdout_sha256=sha(raw)); save()
        if op['exit_code'] != 0:
            raise ValueError(name + ' failed; partial RAM state retained')
        return json.loads(raw)
    def tool(name, *values):
        return [sys.executable, ROOT / 'tools' / name, *values]
    def live(name, command, payload=None, timeout=20):
        arguments = tool('lynx_live_command.py', '--session', args.session, '--name', 'alpine-stage-' + name,
                         '--command', command, '--timeout', str(timeout))
        if payload is not None:
            arguments.extend(['--stdin-file', payload])
        result = run(name, arguments, timeout=timeout + 35)
        p = Path(result['result'])
        receipt = json.loads(p.read_text())
        operation = next(item for item in receipt['operations'] if item['name'] == 'command')
        raw = p.with_name('command.stdout').read_bytes()
        if not receipt.get('native_identity_verified') or operation['exit_code'] != 0 or sha(raw) != operation['stdout_sha256']:
            raise ValueError('Fresh identity or capture hash failed')
        report['operations'][-1]['live_receipt'] = str(p); save()
        return raw.decode()
    try:
        before = run('power-before', tool('configure_runtime_power.py', '--session', args.session, '--verify-only'))
        if before['state'] != 'ready':
            raise ValueError('Working power runtime required')
        boot_id = str(uuid.UUID(json.loads(Path(before['result']).read_text())['boot_id']))
        report['boot_id'] = boot_id
        guard = 'set -eu; test "$(cat /proc/sys/kernel/random/boot_id)" = ' + boot_id + '; '
        digest = sha(json.dumps({name: sha(data) for name, data in sorted(members.items())}, sort_keys=True).encode())
        destination = '/run/lynx/alpine-stage-' + digest[:20]
        report['input_destination'] = destination
        preflight = guard + '''awk '$2 == "/run" && $3 == "tmpfs" {good=1} END {exit !good}' /proc/mounts
test ! -L /run/lynx
temperature=$(sed -n 's/^temperature_millidegrees_celsius=//p' /run/lynx/battery-last)
capacity=$(sed -n 's/^capacity_percent=//p' /run/lynx/battery-last)
test "$temperature" -gt 0; test "$temperature" -lt 35000; test "$capacity" -ge 20
test "$(cat /sys/class/power_supply/11e01000.i2c:mt6375@34:chg/online)" = 0
cat /run/lynx/thermal-watch.pid /run/lynx/battery-watch.pid /run/lynx/thermal-cooling-watch/pid
'''
        pids_before = live('preflight', preflight).strip().splitlines()
        if len(pids_before) != 3 or any(not pid.isdigit() for pid in pids_before):
            raise ValueError('Unexpected watcher PID inventory')
        check = guard + 'if [ -e ' + destination + ' ] || [ -L ' + destination + ' ]; then '
        check += 'test -d ' + destination + '; test ! -L ' + destination + '; echo "' + sha(members['inputs.sha256']) + '  ' + destination + '/inputs.sha256" | sha256sum -c -; '
        check += '(cd ' + destination + ' && sha256sum -c inputs.sha256); echo LYNX_STAGE_INPUTS_REUSABLE; else echo LYNX_STAGE_INPUTS_ABSENT; fi'
        existing = live('input-state', check)
        if existing.endswith('LYNX_STAGE_INPUTS_REUSABLE\n'):
            report['input_upload'] = 'reused-verified-existing'
        elif existing == 'LYNX_STAGE_INPUTS_ABSENT\n':
            archive = out / 'inputs.tar'
            archive.write_bytes(pack_inputs(members))
            archive_hash = sha(archive.read_bytes())
            # Refuse partial state; never overwrite or clean failed work.
            upload = guard + 'test ! -e ' + destination + '; test ! -L ' + destination + '; test ! -e ' + destination + '.tar.partial; test ! -L ' + destination + '.tar.partial; '
            upload += "available=$(df -Pk /run | awk 'END {print $4}'); test \"$available\" -ge " + str(32768 + (archive.stat().st_size * 2 + 1023) // 1024) + '; '
            upload += 'cat > ' + destination + '.tar.partial; echo "' + archive_hash + '  ' + destination + '.tar.partial" | sha256sum -c -; mkdir -m 700 ' + destination + '; tar -xf ' + destination + '.tar.partial -C ' + destination
            live('upload', upload, archive, timeout=45)
            report['input_upload'] = 'created-new'
        else:
            raise ValueError('Unexpected input inventory response')
        if args.isolated_replay:
            payload = out / 'replay-source'
            payload.write_bytes(replay)
            archive_hash = sha(pack_inputs(members))
            command = guard + 'echo "' + archive_hash + '  ' + destination + '.tar.partial" | sha256sum -c -; '
            command += '''parent_namespace=$(/bin/busybox readlink /proc/self/ns/mnt)
test "$parent_namespace" = "$(/bin/busybox readlink /proc/1/ns/mnt)"
mounts_before=$(/bin/busybox sha256sum /proc/self/mountinfo)
pid1_before=$(/bin/busybox sha256sum /proc/1/exe)
'''
            command += '/bin/busybox unshare -m --propagation private /bin/busybox sh -s -- ' + boot_id + ' "$parent_namespace" 3< ' + destination + '.tar.partial\n'
            command += '''test "$parent_namespace" = "$(/bin/busybox readlink /proc/self/ns/mnt)"
test "$mounts_before" = "$(/bin/busybox sha256sum /proc/self/mountinfo)"
test "$pid1_before" = "$(/bin/busybox sha256sum /proc/1/exe)"
echo LYNX_ALPINE_ISOLATED_PARENT_PRESERVED
'''
            proof = live('run', command, payload, timeout=55)
            marker = 'LYNX_ALPINE_ISOLATED_COLD_REPLAY_PASS\n'
            if 'LYNX_ALPINE_ISOLATED_PARENT_PRESERVED\n' not in proof:
                raise ValueError('Parent runtime not verified after isolated replay')
        else:
            stage_mode = '--install' if args.install else '--verify'
            proof = live('run', guard + '/bin/busybox sh ' + destination + '/stage.sh ' + shlex.join([stage_mode, boot_id, destination]), timeout=55)
            marker = 'LYNX_ALPINE_RUNTIME_STAGE_READY\n'
        if marker not in proof:
            raise ValueError('Missing stage success marker')
        after = run('power-after', tool('configure_runtime_power.py', '--session', args.session, '--verify-only'))
        if after['state'] != 'ready' or json.loads(Path(after['result']).read_text())['boot_id'] != boot_id:
            raise ValueError('Original power runtime not verified after stage')
        pids_after = live('watchers-after', guard + 'cat /run/lynx/thermal-watch.pid /run/lynx/battery-watch.pid /run/lynx/thermal-cooling-watch/pid').strip().splitlines()
        if pids_after != pids_before:
            raise ValueError('Watcher PID inventory changed')
        report.update(state='isolated-replay-verified' if args.isolated_replay else 'native-userspace-verified', native_rootfs_verified=True,
                      original_runtime_verified=True, rootfs_left_in_ram=not args.isolated_replay, watcher_pids_unchanged=True)
    except Exception as error:
        report.update(state='failed', error=str(error))
    report['finished_ns'] = time.time_ns(); save()
    print(json.dumps({'state': report['state'], 'result': str(out / 'result.json')}))
    if report['state'] not in ['native-userspace-verified', 'isolated-replay-verified']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
