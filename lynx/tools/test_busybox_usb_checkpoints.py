"""Exercise the exact shell helpers with deterministic USB/module failures."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parent.parent


def main():
    output = ROOT / 'tools/test-artifacts' / ('busybox-usb-checkpoints-' + str(time.time_ns()))
    output.mkdir()
    fake = output / 'busybox'
    fake.write_text('''#!/usr/bin/python3
import json, os, pathlib, sys
r=pathlib.Path(os.environ['LYNX_FIXTURE'])
op=sys.argv[1:]
with (r/'calls.jsonl').open('a') as f: f.write(json.dumps(op)+'\\n')
if op[0]=='cat':
    try: sys.stdout.write(pathlib.Path(op[1]).read_text())
    except OSError: sys.exit(1)
elif op[0]=='sleep':
    count=len([x for x in (r/'calls.jsonl').read_text().splitlines() if json.loads(x)[0]=='sleep'])
    if str(count)==os.environ.get('LYNX_CONFIGURE_AFTER'): (r/'state').write_text('configured\\n')
elif op[0]=='insmod':
    sys.exit(1 if pathlib.Path(op[1]).name==os.environ.get('LYNX_FAIL_MODULE') else 0)
else: sys.exit(2)
''')
    fake.chmod(0o755)
    enumeration = ROOT / 'linux-port/usb-enumeration-check.sh'
    modules = ROOT / 'linux-port/usb-module-checkpoint.sh'
    cases = []
    for name, initial, after, expected in [('already-configured', 'configured', '', 0),
                                          ('never-enumerates', 'not attached', '', 1),
                                          ('enumerates-later', 'powered', '3', 0),
                                          ('missing-state', None, '', 1)]:
        folder = output / name
        folder.mkdir()
        if initial is not None:
            (folder / 'state').write_text(initial + '\n')
        env = dict(os.environ, BB=str(fake), LYNX_FIXTURE=str(folder), LYNX_CONFIGURE_AFTER=after)
        process = subprocess.run(['sh', '-c', '. "$1"; lynx_wait_usb_configured "$2"', 'fixture', str(enumeration), str(folder)], env=env, capture_output=True, text=True, timeout=5)
        calls = [json.loads(line) for line in (folder / 'calls.jsonl').read_text().splitlines()]
        sleeps = sum(call[0] == 'sleep' for call in calls)
        assert process.returncode == expected, (name, process.stderr)
        assert sleeps == {'already-configured': 0, 'never-enumerates': 30, 'enumerates-later': 3, 'missing-state': 0}[name]
        cases.append(dict(name=name, exit_code=process.returncode, sleep_calls=sleeps))
    for name, fail, expected, loaded in [('all-loads-complete', '', 0, 3), ('failed-load-stops', 'two.ko', 1, 2)]:
        folder = output / name
        folder.mkdir()
        (folder / 'modules').write_text('one.ko\n\ntwo.ko\nthree.ko\n')
        env = dict(os.environ, BB=str(fake), LYNX_FIXTURE=str(folder), LYNX_FAIL_MODULE=fail)
        process = subprocess.run(['sh', '-c', 'log() { printf "%s\\n" "$*"; }; . "$1"; lynx_load_checkpoint_modules "$2"', 'fixture', str(modules), str(folder / 'modules')], env=env, capture_output=True, text=True, timeout=5)
        (folder / 'shell-output.txt').write_text(process.stdout + process.stderr)
        calls = [json.loads(line) for line in (folder / 'calls.jsonl').read_text().splitlines()]
        assert process.returncode == expected
        assert calls == [['insmod', '/lib/modules/' + mod] for mod in ['one.ko', 'two.ko', 'three.ko'][:loaded]]
        if fail:
            assert 'CHECKPOINT_MODULE_FAILED two.ko' in process.stdout and 'CHECKPOINT_MODULE_OK two.ko' not in process.stdout
        cases.append(dict(name=name, exit_code=process.returncode, attempted_modules=loaded))
    report = dict(passed=True, phone_contacted=False, cases=cases,
                  sources={str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in [enumeration, modules]},
                  limits='Host shell fixtures validate bounded failure behavior; real USB hardware and module probe timing are not emulated.')
    (output / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print('Six shell fixtures passed:', output / 'result.json')


if __name__ == '__main__':
    main()
