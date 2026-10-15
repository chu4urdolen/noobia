"""Build/inspect the diagnostic through Kbuild; never load it on a handset."""
import argparse
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PORT = ROOT / 'linux-port'
sys.path.insert(0, str(PORT))
from image_formats import elf64, module_metadata


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--basis', type=Path, required=True)
    args = parser.parse_args()
    out = args.basis.resolve()
    info = json.loads((out / 'result.json').read_text())
    basis, module = Path(info['basis']), Path(info['module'])
    compiler = Path(info['compiler'])
    env = dict(os.environ)
    env.update(PATH=str(compiler / 'bin') + ':' + env['PATH'], TMPDIR=str(out))
    common = ['make', '-j4', 'ARCH=arm64', 'LLVM=1', 'LLVM_IAS=1',
              'CLANG_TRIPLE=aarch64-linux-gnu-',
              'CROSS_COMPILE=' + str(ROOT / 'tools/aarch64-gcc/root/usr/bin/aarch64-linux-gnu-'),
              'M=' + str(module)]
    record = {'phone_contacted': False, 'module_loaded': False, 'passed': False,
              'started_ns': time.time_ns(), 'operations': [],
              'source_sha256': sha((module / 'lynx-gauge-sample.c').read_bytes())}
    receipt = out / 'build-result.json'
    if receipt.exists():
        prior = out / 'build-attempts' / str(time.time_ns())
        prior.mkdir(parents=True, mode=0o700)
        previous = json.loads(receipt.read_text())
        shutil.copyfile(receipt, prior / receipt.name)
        for operation in previous.get('operations', []):
            for suffix in ['stdout', 'stderr']:
                name = operation['name'] + '.' + suffix
                if (out / name).exists():
                    shutil.copyfile(out / name, prior / name)

    def save():
        receipt.write_text(json.dumps(record, indent=2) + '\n')

    def run(name, command):
        operation = {'name': name, 'command': command, 'started_ns': time.time_ns()}
        record['operations'].append(operation)
        save()
        with (out / (name + '.stdout')).open('wb') as stdout, (out / (name + '.stderr')).open('wb') as stderr:
            p = subprocess.run(command, cwd=basis, env=env, stdout=stdout, stderr=stderr, timeout=180)
        operation.update(exit_code=p.returncode, finished_ns=time.time_ns())
        save()
        if p.returncode:
            raise ValueError(name + ' failed; saved complete stdout/stderr')

    try:
        run('host-tools', common + ['-f', 'Makefile.lynx', 'lynx-host-tools'])
        run('module', common + ['modules'])
        data = (module / 'lynx-gauge-sample.ko').read_bytes()
        sections = elf64(data)['sections']
        metadata = module_metadata(data)['values']
        expected = '5.10.149-android12-9-o-g311738fbb5a8 SMP preempt mod_unload modversions aarch64'
        if metadata.get('vermagic') != [expected] or metadata.get('license') != ['GPL']:
            raise ValueError('Unexpected module kernel identity/license')
        if metadata.get('alias'):
            raise ValueError('Diagnostic must not autoload')
        evidence = json.loads((out / 'stock-import-provenance.json').read_text())
        imports = {}
        for crc, raw in struct.iter_unpack('<Q56s', sections.get('__versions', b'')):
            name = raw.split(b'\0')[0].decode()
            if name not in evidence or int(evidence[name]['crc'], 16) != crc:
                raise ValueError('Import lacks exact stock CRC evidence: ' + name)
            imports[name] = f'{crc:08x}'
        if 'module_layout' not in imports or 'i2c_smbus_read_word_data' not in imports:
            raise ValueError('Expected versioned imports absent')
        cmd = (module / '.lynx-gauge-sample.o.cmd').read_text()
        if '-flto' not in cmd or '-fsanitize=cfi' not in cmd:
            raise ValueError('LTO/CFI compile flags missing')
        run('defined-symbols', [str(compiler / 'bin/llvm-nm'), '--defined-only', str(module / 'lynx-gauge-sample.ko')])
        symbols = (out / 'defined-symbols.stdout').read_text()
        if not re.search(r'(?m)^[0-9a-f]+ T __cfi_check$', symbols) or '__cfi_jt_init_module' not in symbols:
            raise ValueError('CFI check/jump-table symbols missing')
        run('undefined-symbols', [str(compiler / 'bin/llvm-nm'), '-u', str(module / 'lynx-gauge-sample.ko')])
        record.update(passed=True, module_sha256=sha(data), module_bytes=len(data),
                      imports=imports, metadata=metadata, lto_and_cfi_enabled=True,
                      limits='Build and static checks only. Runtime CFI/module loading and physical gauge behavior untested.')
    except Exception as error:
        record['error'] = str(error)
    record['finished_ns'] = time.time_ns()
    save()
    print(json.dumps({'result': str(receipt), 'passed': record['passed'],
                      'error': record.get('error'), 'module_sha256': record.get('module_sha256')}, indent=2))
    if not record['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
