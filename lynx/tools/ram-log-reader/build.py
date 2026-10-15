"""Compile only offline reader/test components using the isolated cross compiler."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

BASE = Path(__file__).resolve().parent
ROOT = BASE.parent / 'aarch64-gcc/root'
compiler = ROOT / 'usr/bin/aarch64-linux-gnu-gcc-13'
env = dict(os.environ, LD_LIBRARY_PATH=str(ROOT / 'usr/lib/x86_64-linux-gnu'))
options = ['-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-ffreestanding',
           '-fno-builtin', '-fno-stack-protector', '-fno-unwind-tables', '-fno-asynchronous-unwind-tables']
commands = [
    ['cc', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-DLYNX_HOST_TEST',
     str(BASE / 'reader.c'), str(BASE / 'test_reader.c'), '-o', str(BASE / 'test_reader')],
    [str(BASE / 'test_reader')],
    [str(compiler), *options, '-mcmodel=tiny', '-fpie', '-c', str(BASE / 'reader.c'),
     '-o', str(BASE / 'reader-aarch64.o')],
    [str(compiler), *options, '-mcmodel=tiny', '-fpie', '-DLYNX_HOST_TEST', '-c', str(BASE / 'reader.c'),
     '-o', str(BASE / 'reader-test-aarch64.o')],
    [str(compiler), *options, '-DLYNX_ARM_TEST', '-c', str(BASE / 'test_reader.c'),
     '-o', str(BASE / 'test-driver-aarch64.o')],
    [str(compiler), *options, '-c', str(BASE / 'test_runtime.c'), '-o', str(BASE / 'test-runtime-aarch64.o')],
    [str(compiler), '-nostdlib', '-static', '-no-pie', '-Wl,-e,_start', '-Wl,--build-id=none',
     str(BASE / 'reader-test-aarch64.o'), str(BASE / 'test-driver-aarch64.o'),
     str(BASE / 'test-runtime-aarch64.o'), '-o', str(BASE / 'test-reader-aarch64')],
]
results = []
for command in commands:
    run = subprocess.run(command, env=env, capture_output=True, text=True, timeout=30)
    results.append({'command': command, 'exit_code': run.returncode, 'output': run.stdout + run.stderr})
    if run.returncode:
        print(run.stdout + run.stderr)
        raise SystemExit(run.returncode)
report = {'commands': results, 'compiler_sha256': hashlib.sha256(compiler.read_bytes()).hexdigest(),
          'files': {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                    for path in BASE.iterdir() if path.is_file() and path.name != 'build-report.json'},
          'host_tests_passed': True, 'arm_tests_executed': False, 'device_contacted': False,
          'deployable_da_payload': False,
          'limits': 'Reader callbacks and isolated test ELF only; no loader entry, heap exploit or physical transport integration.'}
(BASE / 'build-report.json').write_text(json.dumps(report, indent=2) + '\n')
print('Host tests passed; ARM64 reader object and isolated test executable built. No deployable DA payload.')
