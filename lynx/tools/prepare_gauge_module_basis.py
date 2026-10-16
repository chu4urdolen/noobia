"""Assemble an external-module basis from exact headers and pinned Kbuild.

No kernel rebuild/config regeneration, handset access, or module loading.
Only regular archive members are copied; no archive links are followed.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tarfile
import time
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent.parent
PORT = ROOT / 'linux-port'
sys.path.insert(0, str(PORT))
from image_formats import elf64

RELEASE = '5.10.149-android12-9-o-g311738fbb5a8'
HEADER_SHA = 'a4d9e0f432ccc34a4b2a71f3f952354172e18ce0e5de2bde6719bc9f60a383f8'
KERNEL = '81ec42ad5e803be0cba619f9f7bb298db7d33d7b'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def put(folder, name, data, executable=False):
    path = folder / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    path.chmod(0o700 if executable else 0o600)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--inputs', type=Path, required=True)
    parser.add_argument('--source-tree', type=Path, help='Optional clean sparse checkout of the pinned source; avoids full archive download')
    parser.add_argument('--reader-source', type=Path, default=PORT / 'lynx-gauge-sample.c')
    parser.add_argument('--module-name', default='lynx-gauge-sample')
    args = parser.parse_args()
    if not re.fullmatch('[a-z][a-z0-9-]+', args.module_name):raise ValueError('Invalid module name')
    inputs = json.loads((args.inputs / 'result.json').read_text())
    compiler = next(r for r in inputs['sources'] if r['name'] == 'clang')
    if not compiler.get('compiler_identity_verified'):
        raise ValueError('Input identity not verified')
    if args.source_tree:
        tree = args.source_tree.resolve()
        commit = subprocess.run(['git', '-C', str(tree), 'rev-parse', 'HEAD'], capture_output=True, check=True).stdout.decode().strip()
        subprocess.run(['git', '-C', str(tree), 'diff', '--quiet', 'HEAD'], check=True)
        if commit != KERNEL:
            raise ValueError('Sparse source commit differs')
    else:
        kernel = next(r for r in inputs['sources'] if r['name'] == 'kernel')
        if not kernel['url'].endswith('/' + KERNEL):
            raise ValueError('Kernel source identity differs')
        archive = Path(kernel['archive'])
        if sha(archive.read_bytes()) != kernel['sha256']:
            raise ValueError('Pinned source archive changed')
    header = PORT / 'artifacts/stock-embedded-headers-1792102559855818099/kheaders-27525811.tar.xz'
    if sha(header.read_bytes()) != HEADER_SHA:
        raise ValueError('Exact stock header archive changed')
    os.umask(0o077)
    out = PORT / 'artifacts' / ('gauge-module-basis-' + str(time.time_ns()))
    out.mkdir(mode=0o700)
    basis = out / 'basis'
    basis.mkdir()
    stock = PORT / 'artifacts/stock-cph2493-August-eu-ota'
    crcs, origins, conflicts = {}, {}, set()
    for folder in [stock / 'vendor-ramdisk-unpacked/lib/modules', stock / 'wifi-reference/vendor-dlkm-unpacked/lib/modules']:
        for module in sorted(folder.glob('*.ko')):
            for crc, raw in struct.iter_unpack('<Q56s', elf64(module.read_bytes())['sections'].get('__versions', b'')):
                name = raw.split(b'\0')[0].decode()
                if name in crcs and crcs[name] != crc:
                    conflicts.add(name)
                crcs[name] = crc
                origins.setdefault(name, []).append(module.name)
    exports = {}
    copied = []
    export_pattern = re.compile(rb'\bEXPORT_SYMBOL(_GPL|_NS_GPL|_NS)?\s*\(\s*(\w+)\s*(?:,\s*(\w+)\s*)?\)')
    def source_files():
        if args.source_tree:
            for path in sorted(tree.rglob('*')):
                if path.is_file() and not path.is_symlink() and path.name != '.git':
                    yield path.relative_to(tree).as_posix(), path.read_bytes(), bool(path.stat().st_mode & 0o111)
            return
        with tarfile.open(archive, 'r:gz') as source:
          for member in source:
            path = PurePosixPath(member.name)
            if path.is_absolute() or '..' in path.parts:
                raise ValueError('Unsafe source member')
            parts = path.parts
            if len(parts) < 2 or not member.isfile():
                continue
            name = '/'.join(parts[1:])
            yield name, source.extractfile(member).read(), bool(member.mode & 0o111)
    for name, data, executable in source_files():
            needed = (name in ['Makefile', 'Kbuild', 'arch/arm64/Makefile', 'arch/arm64/Makefile.postlink']
                      or name.startswith('scripts/') or name.startswith('tools/include/'))
            if needed or name.endswith(('.c', '.h', '.S')):
                if needed:
                    put(basis, name, data, executable)
                    copied.append({'path': name, 'sha256': sha(data)})
                if b'EXPORT_SYMBOL' in data:
                    for suffix, symbol, namespace in export_pattern.findall(data):
                        symbol = symbol.decode()
                        if symbol in crcs and symbol not in conflicts:
                            kind = 'EXPORT_SYMBOL_GPL' if b'GPL' in suffix else 'EXPORT_SYMBOL'
                            exports.setdefault(symbol, []).append({'source': name, 'kind': kind,
                                                                    'namespace': namespace.decode()})
                    if name == 'drivers/base/core.c':
                        # This pinned source exports logging helpers through a
                        # constructor macro rather than literal symbol names.
                        body = data.split(b'#define define_dev_printk_level(func, kern_level)', 1)[1].split(b'define_dev_printk_level(_dev_emerg,', 1)[0]
                        if b'EXPORT_SYMBOL(func);' not in body:
                            raise ValueError('Logging export macro differs')
                        for raw_symbol in re.findall(rb'(?m)^define_dev_printk_level\((_dev_\w+),\s*KERN_\w+\);', data):
                            symbol = raw_symbol.decode()
                            if symbol in crcs and symbol not in conflicts:
                                exports.setdefault(symbol, []).append({'source': name, 'kind': 'EXPORT_SYMBOL',
                                                                        'namespace': '', 'macro': 'define_dev_printk_level'})
                    if name == 'kernel/params.c':
                        body=data.split(b'#define STANDARD_PARAM_DEF(name, type, format, strtolfn)',1)[1].split(b'STANDARD_PARAM_DEF(byte,',1)[0]
                        if b'EXPORT_SYMBOL(param_ops_##name)' not in body:raise ValueError('Parameter export macro differs')
                        for short in re.findall(rb'(?m)^STANDARD_PARAM_DEF\((\w+),',data):
                            symbol='param_ops_'+short.decode()
                            if symbol in crcs and symbol not in conflicts:
                                exports.setdefault(symbol,[]).append({'source':name,'kind':'EXPORT_SYMBOL','namespace':'','macro':'STANDARD_PARAM_DEF'})
    header_files = []
    with tarfile.open(header, 'r:xz') as headers:
        for member in headers:
            name = str(PurePosixPath(member.name))
            if name.startswith('/') or '..' in PurePosixPath(name).parts:
                raise ValueError('Unsafe header member')
            if member.isfile():
                data = headers.extractfile(member).read()
                put(basis, name, data)
                header_files.append({'path': name, 'sha256': sha(data)})
    config = (stock / 'kernel-config.txt').read_bytes()
    put(basis, '.config', config)
    put(basis, 'include/config/auto.conf', b'\n'.join(line for line in config.splitlines() if line.startswith(b'CONFIG_')) + b'\n')
    put(basis, 'include/config/kernel.release', (RELEASE + '\n').encode())
    if RELEASE not in (basis / 'include/generated/utsrelease.h').read_text():
        raise ValueError('Exact stock release header missing')
    lines, provenance = [], {}
    for symbol, definitions in sorted(exports.items()):
        choices = {(d['kind'], d['namespace']) for d in definitions}
        if len(choices) != 1:
            continue  # Ambiguous source export visibility: no guessed entry.
        kind, namespace = next(iter(choices))
        lines.append(f'0x{crcs[symbol]:08x}\t{symbol}\tvmlinux\t{kind}\t{namespace}\n')
        provenance[symbol] = {'crc': f'{crcs[symbol]:08x}', 'stock_importers': origins[symbol],
                              'reference_export_definitions': definitions}
    put(basis, 'Module.symvers', ''.join(lines).encode())
    # Additive wrapper only; stock Makefile and scripts stay unmodified. M=
    # causes Kbuild to treat the prepared kernel as read-only (no syncconfig).
    put(basis, 'Makefile.lynx', b'include Makefile\n.PHONY: lynx-host-tools\nlynx-host-tools: scripts_basic\n\t$(Q)$(MAKE) $(build)=scripts/mod\n\t$(Q)$(MAKE) $(build)=scripts scripts/module.lds\n')
    module = out / 'module'
    module.mkdir()
    shutil.copyfile(args.reader_source, module / (args.module_name+'.c'))
    put(module, 'Makefile', ('obj-m := '+args.module_name+'.o\n').encode())
    (out / 'header-inventory.json').write_text(json.dumps(header_files, indent=2) + '\n')
    (out / 'kbuild-inventory.json').write_text(json.dumps(copied, indent=2) + '\n')
    (out / 'stock-import-provenance.json').write_text(json.dumps(provenance, indent=2) + '\n')
    report = {'phone_contacted': False, 'kernel_configuration_regenerated': False,
              'modules_built_or_loaded': False, 'basis': str(basis), 'module': str(module),
              'compiler': compiler['destination'], 'kernel_commit': KERNEL, 'reader_source': str(args.reader_source.resolve()), 'module_name':args.module_name,
              'header_sha256': HEADER_SHA, 'symbol_entries': len(lines),
              'conflicting_stock_imports_excluded': sorted(conflicts),
              'limits': 'Partial export table: genuine stock import CRCs plus unambiguous published reference export declarations. Unobserved/ambiguous symbols are absent and must cause build failure. Not proof of runtime CFI/ABI or hardware safety.'}
    (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'result': str(out / 'result.json'), 'symbol_entries': len(lines)}, indent=2))


if __name__ == '__main__':
    main()
