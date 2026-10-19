"""Build V33: give PID 1 valid standard descriptors before its Alpine guard.

Derive only primary /init from the hardware-booted V32. Keep its stock kernel,
supplementary payload, boot tail, recovery boundaries and all other members.
No phone contact or flash occurs.
"""
import hashlib
import json
import os
from pathlib import Path
import stat
import struct
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
PORT = ROOT / 'linux-port'
BASE = PORT / 'artifacts/persistent-openrc-v32-offline'
OUT = PORT / 'artifacts/persistent-openrc-v33-offline'
sys.path.insert(0, str(PORT))
from image_formats import read_boot_v4, read_newc, require
from prepare_busybox_diagnostics import pack
from ramdisk_codec import decompress

V32_SHA = 'be92a0c7de4c1755a0cf11732c875e388e80339aca763c9073ae122ecddd11c5'
OLD = b'exec 2>>/run/lynx/openrc-pid1-stderr.log\n'
NEW = (b'exec </dev/null 1>>/run/lynx/openrc-pid1-stdout.log '
       b'2>>/run/lynx/openrc-pid1-stderr.log\n')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    os.umask(0o077)
    require(not OUT.exists(), 'Refuse to overwrite V33 candidate')
    source = (BASE / 'nord3-persistent-openrc-v32-untested.img').read_bytes()
    build = json.loads((BASE / 'build-result.json').read_text())
    validation = json.loads((BASE / 'validation.json').read_text())
    require(sha(source) == V32_SHA == build['image_sha256'] == validation['image_sha256'],
            'Hardware-booted V32 parent differs')
    recipe = json.loads((PORT / 'known-good-v19/recipe.json').read_text())
    offset, coverage = recipe['payload_offset'], recipe['coverage_bytes']
    boot = read_boot_v4(source)
    primary = read_newc(decompress(boot['ramdisk']))
    init = primary['init']['data']
    require(init.count(OLD) == 1, 'V32 stdio site differs')
    new_init = init.replace(OLD, NEW)
    primary['init'] = {**primary['init'], 'data': new_init}
    ramdisk = pack(dict(sorted(primary.items(), key=lambda pair: (
        not stat.S_ISDIR(pair[1]['mode']), pair[0].count('/'), pair[0]))))
    header = bytearray(source[:1584])
    struct.pack_into('<I', header, 12, len(ramdisk))
    align = lambda value: (value + 4095) // 4096 * 4096
    loaded = (bytes(header).ljust(4096, b'\0') +
              boot['kernel'].ljust(align(len(boot['kernel'])), b'\0') +
              ramdisk.ljust(align(len(ramdisk)), b'\0'))
    require(len(loaded) <= coverage <= offset, 'Primary overlaps payload')
    candidate = loaded.ljust(coverage, b'\0') + source[coverage:]
    require(len(candidate) == len(source) == 67_108_864, 'Image size differs')
    require(candidate[offset:] == source[offset:], 'Supplement or boot tail changed')
    checked = read_boot_v4(candidate)
    require(checked['kernel'] == boot['kernel'] and checked['cmdline'] == boot['cmdline'],
            'Stock kernel or cmdline changed')
    require(candidate[:12] == source[:12] and candidate[16:4096] == source[16:4096],
            'Header changed outside ramdisk length')
    checked_entries = read_newc(decompress(checked['ramdisk']))
    original_entries = read_newc(decompress(boot['ramdisk']))
    require(set(checked_entries) == set(original_entries), 'Primary member set differs')
    for name, entry in original_entries.items():
        if name != 'init':
            require(checked_entries[name] == entry, 'Unrelated primary change: ' + name)
    require(checked_entries['init']['data'] == new_init, 'Init roundtrip differs')
    OUT.mkdir(mode=0o700)
    image = OUT / 'nord3-persistent-openrc-v33-untested.img'
    image.write_bytes(candidate)
    image.chmod(0o600)
    (OUT / 'init-source').write_bytes(new_init)
    result = {'state': 'offline-stdio-fix-candidate-built',
              'created_ns': time.time_ns(), 'parent_v32_sha256': V32_SHA,
              'image_sha256': sha(candidate), 'image_bytes': len(candidate),
              'init_sha256': sha(new_init), 'changed_members': ['init'],
              'supplement_identical_to_v32': True,
              'stock_kernel_sha256': sha(boot['kernel']),
              'phone_contacted': False, 'flash_performed': False,
              'limit': 'Host and RAM proof only; hardware V33 boot and Alpine PID 1 untested.'}
    (OUT / 'build-result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'state': result['state'], 'result': str(OUT / 'build-result.json')}))


if __name__ == '__main__':
    main()
