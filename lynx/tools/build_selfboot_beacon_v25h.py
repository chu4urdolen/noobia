"""Build V25h from exact V25g, changing only local Wi-Fi discovery.

This is an offline candidate. It does not contact Lynx or authorize a flash.
"""
import gzip
import json
import os
from pathlib import Path
import struct
import sys
import time

import build_health_stage_candidate as stage

ROOT, PORT = stage.ROOT, stage.PORT
SOURCE = PORT / 'artifacts/selfboot-compact-v25g-offline'
OUT = PORT / 'artifacts/selfboot-beacon-v25h-offline'
SOURCE_SHA = '84b037a79eb678524a88e8c66ced214502ea5381193df26e2c7cec024083bebe'
MEMBER = 'etc/lynx/wifi-local-supervise.sh'
sys.path.insert(0, str(PORT))
from image_formats import read_boot_v4, read_newc, require
from ramdisk_codec import decompress


def main():
    os.umask(0o077)
    require(not OUT.exists(), 'Refuse to replace V25h prototype')
    parent = json.loads((SOURCE / 'build-result.json').read_text())
    source = (SOURCE / 'nord3-selfboot-compact-untested.img').read_bytes()
    require(parent['image_sha256'] == stage.sha(source) == SOURCE_SHA,
            'V25g source differs')
    recipe = json.loads((PORT / 'known-good-v19/recipe.json').read_text())
    offset = recipe['payload_offset']
    boot = read_boot_v4(source)
    primary = read_newc(decompress(boot['ramdisk']))
    old_primary = {name: dict(entry) for name, entry in primary.items()}
    old_payload = source[offset:offset + parent['payload_bytes']]
    require(stage.sha(old_payload) == parent['payload_sha256'],
            'V25g supplement differs')
    supplement = read_newc(gzip.decompress(old_payload))
    old_supplement = {name: dict(entry) for name, entry in supplement.items()}
    replacement = (PORT / 'lynx-wifi-local-supervise.sh').read_bytes()
    require(replacement.startswith(b'#!/bin/sh\n') and MEMBER in supplement,
            'Local supervisor source or package differs')
    require(replacement != supplement[MEMBER]['data'],
            'Local supervisor has no change')
    supplement[MEMBER] = {**supplement[MEMBER], 'data': replacement}
    new_payload = gzip.compress(decompress(stage.packed(supplement)),
                                compresslevel=9, mtime=0)
    require(len(new_payload) < 40_000_000, 'Payload exceeds loader bound')
    primary['etc/lynx/payload-bytes'] = {
        **primary['etc/lynx/payload-bytes'],
        'data': (str(len(new_payload)) + '\n').encode()}
    primary['etc/lynx/payload-sha256'] = {
        **primary['etc/lynx/payload-sha256'],
        'data': (stage.sha(new_payload) + '\n').encode()}
    ramdisk = stage.packed(primary)
    header = bytearray(source[:1584])
    struct.pack_into('<I', header, 12, len(ramdisk))
    align = lambda value: (value + 4095) // 4096 * 4096
    loaded = (bytes(header).ljust(4096, b'\0') +
              boot['kernel'].ljust(align(len(boot['kernel'])), b'\0') +
              ramdisk.ljust(align(len(ramdisk)), b'\0'))
    coverage = recipe['coverage_bytes']
    require(len(loaded) <= coverage <= offset and
            offset + max(len(old_payload), len(new_payload)) < len(source) - 4096,
            'V25h overlaps boot image boundaries')
    image = bytearray(loaded.ljust(coverage, b'\0') + source[coverage:])
    image[offset:offset + max(len(old_payload), len(new_payload))] = (
        new_payload.ljust(max(len(old_payload), len(new_payload)), b'\0'))
    image = bytes(image)
    require(len(image) == 67108864, 'V25h image size differs')
    checked_boot = read_boot_v4(image)
    require(checked_boot['kernel'] == boot['kernel'] and
            checked_boot['cmdline'] == boot['cmdline'] and
            image[:12] == source[:12] and image[16:4096] == source[16:4096],
            'V25h changed kernel or unrelated boot header')
    checked_primary = read_newc(decompress(checked_boot['ramdisk']))
    require(set(checked_primary) == set(old_primary) and
            checked_primary['init'] == old_primary['init'],
            'V25h changed primary init or members')
    for name, entry in old_primary.items():
        if name not in ('etc/lynx/payload-bytes', 'etc/lynx/payload-sha256'):
            require(checked_primary[name] == entry,
                    'V25h changed unrelated primary member: ' + name)
    require(checked_primary['etc/lynx/payload-sha256']['data'].strip().decode() ==
            stage.sha(new_payload), 'V25h payload hash metadata differs')
    checked_supplement = read_newc(gzip.decompress(
        image[offset:offset + len(new_payload)]))
    require(set(checked_supplement) == set(old_supplement),
            'V25h changed supplement member set')
    for name, entry in old_supplement.items():
        if name == MEMBER:
            require(checked_supplement[name]['data'] == replacement,
                    'V25h beacon script round trip differs')
        else:
            require(checked_supplement[name] == entry,
                    'V25h changed unrelated supplement member: ' + name)
    OUT.mkdir(mode=0o700)
    target = OUT / 'nord3-selfboot-beacon-untested.img'
    target.write_bytes(image)
    target.chmod(0o600)
    report = {
        'state': 'offline-selfboot-beacon-candidate-untested',
        'variant': 'V25h-beacon', 'created_ns': time.time_ns(),
        'image_sha256': stage.sha(image), 'image_bytes': len(image),
        'parent_v25g_sha256': SOURCE_SHA,
        'stock_kernel_sha256': stage.sha(checked_boot['kernel']),
        'init_sha256': stage.sha(checked_primary['init']['data']),
        'payload_sha256': stage.sha(new_payload), 'payload_bytes': len(new_payload),
        'changed_supplement_member': MEMBER,
        'new_supervisor_sha256': stage.sha(replacement),
        'phone_contacted': False, 'flash_performed': False,
        'image_mode': '0600',
        'limits': 'Offline discovery change only. No handset boot or health proof; general safety hold remains active.'}
    (OUT / 'build-result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'state': report['state'], 'image_sha256': report['image_sha256'],
                      'payload_bytes': len(new_payload),
                      'result': str(OUT / 'build-result.json')}))


if __name__ == '__main__':
    main()
