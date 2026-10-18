"""Build V25g by removing unused Alpine/OpenRC payload from diagnostic V25f.

This keeps the exact V25f init and guarded health-first diagnostic behavior,
but brings the boot_a supplement closer to V19's proven payload size. Alpine
will be packaged only after the BusyBox self-boot path is demonstrated.
"""
import gzip
import json
import os
from pathlib import Path
import stat
import struct
import sys
import time

import build_health_stage_candidate as stage

ROOT, PORT = stage.ROOT, stage.PORT
SOURCE = PORT / 'artifacts/selfboot-wifi-first-v25f-offline'
OUT = PORT / 'artifacts/selfboot-compact-v25g-offline'
sys.path.insert(0, str(PORT))
from image_formats import read_boot_v4, read_newc, require
from ramdisk_codec import decompress

REMOVE = {
    'etc/lynx/openrc-handoff.sh',
    'etc/lynx/openrc-handoff-guard.sh',
    'usr/share/lynx/alpine-openrc-rootfs.cpio.gz',
    'usr/share/lynx/alpine-openrc-rootfs.sha256',
}


def main():
    os.umask(0o077)
    require(not OUT.exists(), 'Refuse to replace V25g prototype')
    parent = json.loads((SOURCE / 'build-result.json').read_text())
    source = (SOURCE / 'nord3-selfboot-health-untested.img').read_bytes()
    require(parent.get('variant') == 'V25f-wifi-first-guarded' and
            stage.sha(source) == parent['image_sha256'] ==
            'e885fb8162e7faf40fba68732fadd77aa3b4328a4b235e4ae4e60873d8feec0d',
            'V25f source differs')
    recipe = json.loads((PORT / 'known-good-v19/recipe.json').read_text())
    offset = recipe['payload_offset']
    boot = read_boot_v4(source)
    primary = read_newc(decompress(boot['ramdisk']))
    old_primary = {name: dict(entry) for name, entry in primary.items()}
    old_payload = source[offset:offset + parent['payload_bytes']]
    require(stage.sha(old_payload) == parent['payload_sha256'],
            'V25f supplement differs')
    supplement = read_newc(gzip.decompress(old_payload))
    old_supplement = {name: dict(entry) for name, entry in supplement.items()}
    require(REMOVE <= set(supplement), 'Expected unused Alpine/OpenRC files absent')
    for name in REMOVE:
        del supplement[name]
    new_payload = gzip.compress(decompress(stage.packed(supplement)), compresslevel=9, mtime=0)
    require(len(new_payload) < parent['payload_bytes'], 'Compaction failed')
    primary['etc/lynx/payload-bytes'] = {
        **primary['etc/lynx/payload-bytes'], 'data': (str(len(new_payload)) + '\n').encode()}
    primary['etc/lynx/payload-sha256'] = {
        **primary['etc/lynx/payload-sha256'], 'data': (stage.sha(new_payload) + '\n').encode()}
    ramdisk = stage.packed(primary)
    header = bytearray(source[:1584])
    struct.pack_into('<I', header, 12, len(ramdisk))
    align = lambda value: (value + 4095) // 4096 * 4096
    loaded = (bytes(header).ljust(4096, b'\0') +
              boot['kernel'].ljust(align(len(boot['kernel'])), b'\0') +
              ramdisk.ljust(align(len(ramdisk)), b'\0'))
    coverage = recipe['coverage_bytes']
    require(len(loaded) <= coverage <= offset and
            offset + len(new_payload) < len(source) - 4096,
            'V25g overlaps boot image boundaries')
    image = bytearray(loaded.ljust(coverage, b'\0') + source[coverage:])
    image[offset:offset + parent['payload_bytes']] = new_payload.ljust(parent['payload_bytes'], b'\0')
    image = bytes(image)
    require(len(image) == 67108864 and read_boot_v4(image)['kernel'] == boot['kernel'],
            'V25g image or kernel differs')
    checked_primary = read_newc(decompress(read_boot_v4(image)['ramdisk']))
    require(checked_primary['init'] == old_primary['init'], 'V25g changed V25f init')
    require(set(checked_primary) == set(old_primary), 'V25g primary member set differs')
    for name, entry in old_primary.items():
        if name not in ('etc/lynx/payload-bytes', 'etc/lynx/payload-sha256'):
            require(checked_primary[name] == entry, 'V25g changed unrelated primary member: ' + name)
    checked_supplement = read_newc(gzip.decompress(image[offset:offset + len(new_payload)]))
    require(set(checked_supplement) == set(old_supplement) - REMOVE,
            'V25g supplement member set differs')
    for name, entry in checked_supplement.items():
        require(entry == old_supplement[name], 'V25g changed retained supplement member: ' + name)
    require(stage.sha(image[:offset]) != stage.sha(source[:offset]),
            'Updated payload metadata was not packed')
    OUT.mkdir(mode=0o700)
    target = OUT / 'nord3-selfboot-compact-untested.img'
    target.write_bytes(image)
    target.chmod(0o600)
    result = {
        'state': 'offline-selfboot-compact-candidate-untested',
        'variant': 'V25g-compact-wifi-first', 'created_ns': time.time_ns(),
        'image_sha256': stage.sha(image), 'image_bytes': len(image),
        'parent_v25f_sha256': parent['image_sha256'],
        'stock_kernel_sha256': stage.sha(boot['kernel']),
        'init_sha256': stage.sha(checked_primary['init']['data']),
        'payload_sha256': stage.sha(new_payload), 'payload_bytes': len(new_payload),
        'removed_unused_members': sorted(REMOVE),
        'phone_contacted': False, 'flash_performed': False,
        'inherits_private_v19_wifi_and_ssh_credentials': True,
        'image_mode': '0600',
        'limits': 'Offline compaction only. No handset boot or health proof. Do not flash under general safety hold without separate review.'}
    (OUT / 'build-result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'state': result['state'], 'image_sha256': result['image_sha256'],
                      'payload_bytes': len(new_payload), 'result': str(OUT / 'build-result.json')}))


if __name__ == '__main__':
    main()
