"""Offline V23 packaging check: reviewed health inputs and scripts, no boot hook.

The image intentionally preserves V22 init byte-for-byte. The packaged startup
script is inert until a separate, reviewed init integration is built and tested.
"""
import gzip
import hashlib
import json
import os
import stat
import struct
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PORT = ROOT / 'linux-port'
BASE = PORT / 'artifacts/openrc-health-v22-offline'
INPUTS = PORT / 'artifacts/autonomous-health-inputs'
OUT = PORT / 'artifacts/health-stage-v23-offline'
sys.path.insert(0, str(PORT))
from image_formats import read_boot_v4, read_newc, require
from prepare_busybox_diagnostics import pack
from ramdisk_codec import decompress


def sha(data):
    return hashlib.sha256(data).hexdigest()


def packed(entries):
    order = dict(sorted(entries.items(), key=lambda pair: (
        not stat.S_ISDIR(pair[1]['mode']), pair[0].count('/'), pair[0])))
    return pack(order)


def put(entries, name, data, mode=0o600):
    for index in range(1, len(Path(name).parts)):
        parent = '/'.join(Path(name).parts[:index])
        entries.setdefault(parent, {'mode': stat.S_IFDIR | 0o755, 'uid': 0, 'gid': 0,
                                    'rdevmajor': 0, 'rdevminor': 0, 'data': b''})
        require(stat.S_ISDIR(entries[parent]['mode']), 'Supplement parent is not a directory: ' + parent)
    require(name not in entries, 'Refuse to replace existing supplement member: ' + name)
    entries[name] = {'mode': stat.S_IFREG | mode, 'uid': 0, 'gid': 0,
                     'rdevmajor': 0, 'rdevminor': 0, 'data': data}


def main():
    os.umask(0o077)
    require(not OUT.exists(), 'Refuse to replace V23 offline image')
    v22 = json.loads((BASE / 'build-result.json').read_text())
    source = (BASE / 'nord3-openrc-health-candidate.img').read_bytes()
    require(v22.get('state') == 'offline-openrc-health-candidate-built' and
            sha(source) == v22['candidate_sha256'] ==
            '01ce287ace2ede31d272a2742f9562284c8b1b8148b8be1abd19b3b4e9068568',
            'V22 source image differs')
    old_payload = (BASE / 'supplement.cpio.gz').read_bytes()
    require(sha(old_payload) == v22['payload_sha256'], 'V22 supplement differs')
    input_manifest = json.loads((INPUTS / 'result.json').read_text())
    input_archive = (INPUTS / 'inputs.tar.gz').read_bytes()
    require(input_manifest.get('state') == 'reviewed-inert-health-inputs' and
            input_manifest.get('roundtrip_verified') and
            sha(input_archive) == input_manifest['archive_sha256'],
            'Reviewed health input pack differs')
    scripts = {}
    for name in ('autonomous-health-preflight.sh', 'autonomous-health-start.sh'):
        data = (PORT / name).read_bytes()
        require(data.startswith(b'#!/bin/sh\n'), 'Health script has unexpected interpreter')
        scripts[name] = data

    boot = read_boot_v4(source)
    primary = read_newc(decompress(boot['ramdisk']))
    require(sha(primary['init']['data']) == v22['init_sha256'], 'V22 init differs')
    supplement = read_newc(gzip.decompress(old_payload))
    put(supplement, 'usr/share/lynx/health-inputs.tar.gz', input_archive)
    put(supplement, 'usr/share/lynx/health-inputs.sha256', (sha(input_archive) + '\n').encode())
    for name, data in scripts.items():
        put(supplement, 'usr/libexec/lynx/' + name, data, 0o700)
    new_payload = gzip.compress(decompress(packed(supplement)), compresslevel=9, mtime=0)
    require(len(new_payload) < 40_000_000, 'V23 payload exceeds exact loader bound')
    primary['etc/lynx/payload-bytes'] = {
        **primary['etc/lynx/payload-bytes'], 'data': (str(len(new_payload)) + '\n').encode()}
    primary['etc/lynx/payload-sha256'] = {
        **primary['etc/lynx/payload-sha256'], 'data': (sha(new_payload) + '\n').encode()}
    ramdisk = packed(primary)
    recipe = json.loads((PORT / 'known-good-v19/recipe.json').read_text())
    header = bytearray(source[:1584])
    struct.pack_into('<I', header, 12, len(ramdisk))
    align = lambda value: (value + 4095) // 4096 * 4096
    loaded = (bytes(header).ljust(4096, b'\0') +
              boot['kernel'].ljust(align(len(boot['kernel'])), b'\0') +
              ramdisk.ljust(align(len(ramdisk)), b'\0'))
    coverage, offset = recipe['coverage_bytes'], recipe['payload_offset']
    require(len(loaded) <= coverage <= offset and
            offset + len(new_payload) < len(source) - 4096,
            'V23 overlaps boot-image boundaries')
    image = bytearray(loaded.ljust(coverage, b'\0') + source[coverage:])
    image[offset:offset + max(len(new_payload), len(old_payload))] = new_payload.ljust(
        max(len(new_payload), len(old_payload)), b'\0')
    image = bytes(image)
    require(len(image) == 67_108_864 and read_boot_v4(image)['kernel'] == boot['kernel'],
            'V23 kernel, header or image size differs')
    check_primary = read_newc(decompress(read_boot_v4(image)['ramdisk']))
    require(check_primary['init']['data'] == primary['init']['data'] and
            check_primary['etc/lynx/payload-sha256']['data'].strip().decode() == sha(new_payload),
            'V23 primary init/payload metadata round trip differs')
    check_supplement = read_newc(gzip.decompress(image[offset:offset + len(new_payload)]))
    require(check_supplement['usr/share/lynx/health-inputs.tar.gz']['data'] == input_archive,
            'V23 health inputs round trip differs')
    for name, data in scripts.items():
        require(check_supplement['usr/libexec/lynx/' + name]['data'] == data,
                'V23 health script round trip differs: ' + name)

    OUT.mkdir(mode=0o700)
    target = OUT / 'nord3-health-stage-inert.img'
    target.write_bytes(image)
    target.chmod(0o600)
    report = {
        'state': 'offline-inert-health-stage-packaged', 'created_ns': time.time_ns(),
        'image_sha256': sha(image), 'image_bytes': len(image),
        'v22_parent_sha256': sha(source), 'stock_kernel_sha256': sha(boot['kernel']),
        'unchanged_init_sha256': sha(primary['init']['data']),
        'supplement_sha256': sha(new_payload), 'supplement_bytes': len(new_payload),
        'health_inputs_sha256': sha(input_archive),
        'scripts': {name: sha(data) for name, data in scripts.items()},
        'auto_boot_hook_present': False, 'phone_contacted': False,
        'flash_performed': False, 'inherits_private_v19_wifi_and_ssh_credentials': True,
        'image_mode': '0600',
        'limits': 'Packaging and round-trip verification only. The startup script is inert; cold-boot loading and thermal safety remain untested. Do not flash while SAFETY-HOLD is active.'}
    (OUT / 'build-result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'state': report['state'], 'image_sha256': report['image_sha256'],
                      'result': str(OUT / 'build-result.json')}))


if __name__ == '__main__':
    main()
