"""Exercise exact shell supervisor with blocked/failed loads and clock faults."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / 'linux-port/mtu3-timed-supervisor.sh'


def main():
    output = ROOT / 'tools/test-artifacts' / ('mtu3-supervisor-' + str(time.time_ns()))
    output.mkdir()
    fake = output / 'busybox'
    fake.write_text('''#!/usr/bin/python3
import json, os, pathlib, shutil, sys, time
r=pathlib.Path(os.environ['LYNX_FIXTURE'])
mode=os.environ['LYNX_CASE']; args=sys.argv[1:]
with (r/'calls.jsonl').open('a') as f: f.write(json.dumps(args)+'\\n')
if args[0]=='mkdir': pathlib.Path(args[-1]).mkdir(parents=True,exist_ok=True)
elif args[0]=='mount': sys.exit(1 if mode=='mount-failure' else 0)
elif args[0]=='mknod':
    if mode=='null-node-failure': sys.exit(1)
    p=pathlib.Path(args[3]); p.parent.mkdir(parents=True,exist_ok=True); p.touch()
elif args[0]=='mv': shutil.move(args[1],args[2])
elif args[0]=='insmod':
    if mode=='pending':
        until=time.monotonic()+10
        while not (r/'release').exists() and time.monotonic()<until: time.sleep(.01)
    sys.exit(7 if mode=='error' else 0)
elif args[0]=='sleep':
    time.sleep(.03)
    p=r/'uptime'; n=int(p.read_text().split('.')[0])+1
    p.write_text('invalid 0\\n' if mode=='clock-failure' and n==3 else str(n)+'.00 0\\n')
else: sys.exit(2)
''')
    fake.chmod(0o755)
    helper = output / 'reboot-stub'
    helper.write_text('''#!/usr/bin/python3
import json, os, pathlib
r=pathlib.Path(os.environ['LYNX_FIXTURE'])
with (r/'reset-calls.jsonl').open('a') as f: f.write(json.dumps({'uptime':r.joinpath('uptime').read_text()})+'\\n')
(r/'release').touch()
''')
    helper.chmod(0o755)
    results = []
    for case, expected_code, expected_deadline in [('success', 0, 20), ('error', 0, 40), ('pending', 0, 60), ('clock-failure', 1, None), ('initial-clock-failure', 1, None), ('mount-failure', 1, None), ('null-node-failure', 1, None)]:
        folder = output / case
        folder.mkdir()
        (folder / 'uptime').write_text('invalid 0\n' if case=='initial-clock-failure' else '0.00 0\n')
        text = SOURCE.read_text().replace('/run', str(folder / 'run')).replace('/proc/uptime', str(folder / 'uptime')).replace('/dev/null', str(folder / 'dev/null')).replace('/bin/boot-proof-reboot', str(helper))
        script = folder / 'supervisor.sh'
        script.write_text('BB="'+str(fake)+'"\nlog() { printf "%s\\n" "$*"; }\n' + text + '\nlynx_mtu3_supervise\n')
        env = dict(os.environ, LYNX_FIXTURE=str(folder), LYNX_CASE=case)
        started = time.monotonic()
        process = subprocess.run(['sh', str(script)], env=env, capture_output=True, text=True, timeout=12)
        (folder / 'stdout.txt').write_text(process.stdout)
        (folder / 'stderr.txt').write_text(process.stderr)
        assert process.returncode == expected_code, (case, process.stderr)
        calls_path = folder / 'reset-calls.jsonl'
        calls = [json.loads(line) for line in calls_path.read_text().splitlines()] if calls_path.exists() else []
        assert len(calls) == (0 if expected_deadline is None else 1), (case, calls)
        if expected_deadline is not None:
            assert int(calls[0]['uptime'].split('.')[0]) == expected_deadline, (case, calls)
            assert process.stdout.count('REQUESTING_ONE_SUPPORTED_BOOTLOADER_REBOOT') == 1
        results.append(dict(case=case, exit_code=process.returncode, reset_calls=len(calls), expected_deadline=expected_deadline, elapsed_seconds=time.monotonic()-started))
    receipt = output / 'result.json'
    receipt.write_text(json.dumps(dict(passed=True, cases=results, source_sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(), phone_contacted=False, real_reboot_executed=False, limits='Host shell fixtures use an accelerated simulated clock and reboot stub; do not prove kernel scheduling or reset viability during an MT6983 probe.'), indent=2) + '\n')
    print('Seven exact-source supervisor cases passed:', receipt)


if __name__ == '__main__':
    main()
