"""Build a private offline V26 Alpine/OpenRC self-boot prototype from V25c.

No handset contact or partition write. This image is not eligible for flashing
under the active thermal safety hold.
"""
import gzip
import json
import os
import struct
import sys
import time

import build_health_stage_candidate as stage

ROOT, PORT = stage.ROOT, stage.PORT
BASE = PORT / 'artifacts/selfboot-health-v25c-offline'
OUT = PORT / 'artifacts/selfboot-alpine-v26-offline'
sys.path.insert(0, str(PORT))
from image_formats import read_boot_v4, read_newc, require
from ramdisk_codec import decompress


OLD_TAIL = b'''log 'LOCAL_SELFBOOT_WIFI_SSH_HEALTH_ACTIVE; BUSYBOX_PID1_RESCUE_READY'
stop
'''
NEW_TAIL = b'''log 'LOCAL_SELFBOOT_WIFI_SSH_HEALTH_ACTIVE; ATTEMPTING_ALPINE_PID1'
. /etc/lynx/openrc-local-handoff.sh || { log 'LOCAL_OPENRC_SCRIPT_LOAD_FAILED; BUSYBOX_RESCUE_ACTIVE'; stop; }
lynx_openrc_local_handoff
log 'LOCAL_OPENRC_HANDOFF_REFUSED; BUSYBOX_RESCUE_ACTIVE'
stop
'''


def main():
    os.umask(0o077)
    require(not OUT.exists(), 'Refuse to replace V26 prototype')
    parent = json.loads((BASE / 'build-result.json').read_text())
    source = (BASE / 'nord3-selfboot-health-untested.img').read_bytes()
    require(parent.get('state') == 'offline-selfboot-health-candidate-untested' and
            stage.sha(source) == parent['image_sha256'] ==
            '587e4e8ec2a195a63a519ce0471003a337faf2d278cba994ee9dd4857b3bcc3a',
            'V25c source differs')
    boot = read_boot_v4(source)
    primary = read_newc(decompress(boot['ramdisk']))
    old_primary = {name: dict(entry) for name, entry in primary.items()}
    old_init = primary['init']['data']
    require(old_init.endswith(OLD_TAIL) and old_init.count(OLD_TAIL) == 1,
            'V25c init handoff site differs')
    new_init = old_init[:-len(OLD_TAIL)] + NEW_TAIL
    primary['init'] = {**primary['init'], 'data': new_init}

    recipe = json.loads((PORT / 'known-good-v19/recipe.json').read_text())
    offset = recipe['payload_offset']
    old_length = parent['payload_bytes']
    old_payload = source[offset:offset + old_length]
    require(stage.sha(old_payload) == parent['payload_sha256'],
            'V25c supplement differs')
    supplement = read_newc(gzip.decompress(old_payload))
    old_supplement = {name: dict(entry) for name, entry in supplement.items()}
    replacements = {
        'etc/lynx/openrc-handoff-guard.sh': PORT / 'openrc-handoff-guard.sh',
    }
    additions = {
        'etc/lynx/openrc-local-handoff.sh': PORT / 'openrc-local-handoff.sh',
    }
    for name, path in replacements.items():
        require(name in supplement, 'Expected V25c guard absent: ' + name)
        data = path.read_bytes()
        require(data.startswith(b'#!/bin/sh\n'), 'Guard interpreter differs')
        supplement[name] = {**supplement[name], 'data': data}
    for name, path in additions.items():
        data = path.read_bytes()
        require(data.startswith(b'#!/bin/sh\n'), 'Handoff interpreter differs')
        stage.put(supplement, name, data, 0o700)
    alpine_archive = supplement['usr/share/lynx/alpine-openrc-rootfs.cpio.gz']['data']
    alpine_hash = supplement['usr/share/lynx/alpine-openrc-rootfs.sha256']['data'].strip().decode()
    require(stage.sha(alpine_archive) == alpine_hash, 'Alpine archive hash differs')
    alpine_root = read_newc(gzip.decompress(alpine_archive))
    require('sbin/openrc-init' in alpine_root and
            'etc/init.d/lynx-health' in alpine_root and
            'etc/runlevels/default/lynx-health' in alpine_root,
            'Alpine health-enabled root is incomplete')
    new_payload = gzip.compress(decompress(stage.packed(supplement)), compresslevel=9, mtime=0)
    require(len(new_payload) < 40_000_000, 'V26 payload exceeds loader bound')
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
            'V26 overlaps boot-image boundaries')
    image = bytearray(loaded.ljust(coverage, b'\0') + source[coverage:])
    image[offset:offset + max(len(new_payload), old_length)] = new_payload.ljust(
        max(len(new_payload), old_length), b'\0')
    image = bytes(image)
    require(len(image) == 67_108_864 and read_boot_v4(image)['kernel'] == boot['kernel'],
            'V26 kernel or image size differs')
    require(image[:12] == source[:12] and image[16:4096] == source[16:4096] and
            read_boot_v4(image)['cmdline'] == boot['cmdline'],
            'V26 boot header changed outside ramdisk length')
    checked_primary = read_newc(decompress(read_boot_v4(image)['ramdisk']))
    require(checked_primary['init']['data'] == new_init and
            checked_primary['etc/lynx/payload-sha256']['data'].strip().decode() == stage.sha(new_payload),
            'V26 init or payload metadata round trip differs')
    require(set(checked_primary) == set(old_primary), 'V26 primary member set differs')
    for name, entry in old_primary.items():
        if name not in ('init', 'etc/lynx/payload-bytes', 'etc/lynx/payload-sha256'):
            require(checked_primary[name] == entry, 'V26 changed unrelated primary member: ' + name)
    checked_supplement = read_newc(gzip.decompress(image[offset:offset + len(new_payload)]))
    require(set(checked_supplement) == set(old_supplement) | set(additions),
            'V26 supplement member set differs')
    for name, entry in old_supplement.items():
        if name not in replacements:
            require(checked_supplement[name] == entry,
                    'V26 changed unrelated supplement member: ' + name)
    for name, path in {**replacements, **additions}.items():
        require(checked_supplement[name]['data'] == path.read_bytes(),
                'V26 script differs after packing: ' + name)

    OUT.mkdir(mode=0o700)
    target = OUT / 'nord3-selfboot-alpine-untested.img'
    target.write_bytes(image)
    target.chmod(0o600)
    result = {
        'state': 'offline-selfboot-alpine-candidate-untested',
        'created_ns': time.time_ns(), 'image_sha256': stage.sha(image),
        'image_bytes': len(image), 'parent_v25c_sha256': stage.sha(source),
        'stock_kernel_sha256': stage.sha(boot['kernel']),
        'new_init_sha256': stage.sha(new_init),
        'payload_sha256': stage.sha(new_payload), 'payload_bytes': len(new_payload),
        'alpine_rootfs_sha256': stage.sha(alpine_archive),
        'alpine_rootfs_bytes': len(alpine_archive),
        'script_sha256': {name: stage.sha(path.read_bytes()) for name, path in
                          {**replacements, **additions}.items()},
        'phone_contacted': False, 'flash_performed': False,
        'inherits_private_v19_wifi_and_ssh_credentials': True, 'image_mode': '0600',
        'limits': 'Offline image only. Local Alpine PID 1 has not run on Lynx. No writable rootfs or safe charging proof. SAFETY-HOLD remains active; DO NOT FLASH.'}
    (OUT / 'build-result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'state': result['state'], 'image_sha256': result['image_sha256'],
                      'result': str(OUT / 'build-result.json')}))


if __name__ == '__main__':
    main()
