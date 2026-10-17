"""Build a PRIVATE offline V24 image with guarded post-SSH health startup.

This builder never contacts Lynx or flashes. SAFETY-HOLD stays active: V24 is
not eligible for a handset trial until its handoff/failure paths are tested.
"""
import gzip
import json
import os
import struct
import sys
import time
from pathlib import Path

import build_health_stage_candidate as stage

ROOT, PORT = stage.ROOT, stage.PORT
BASE = PORT / 'artifacts/health-stage-v23-offline'
OUT = PORT / 'artifacts/autonomous-health-v24-offline'
sys.path.insert(0, str(PORT))
from image_formats import read_boot_v4, read_newc, require
from ramdisk_codec import decompress

OLD_TAIL = b'''log 'WIFI_SUPERVISOR_FINISHED; CHECKING_OPT_IN_OPENRC_GATE'
. /etc/lynx/openrc-handoff.sh || { log 'OPENRC_SCRIPT_LOAD_FAILED; REQUESTING_FASTBOOT'; /bin/boot-proof-reboot; stop; }
lynx_openrc_handoff
log 'OPENRC_HANDOFF_FAILED; REQUESTING_FASTBOOT'
/bin/boot-proof-reboot
stop
'''
NEW_TAIL = b'''log 'WIFI_SUPERVISOR_FINISHED; STARTING_GUARDED_HEALTH'
. /etc/lynx/autonomous-health-handoff.sh || { log 'HEALTH_HANDOFF_SCRIPT_LOAD_FAILED'; $BB poweroff -f; /bin/boot-proof-reboot; stop; }
lynx_autonomous_health_handoff
log 'HEALTH_OR_OPENRC_HANDOFF_FAILED; POWER_OFF_REQUESTED'
$BB poweroff -f
/bin/boot-proof-reboot
stop
'''


def main():
    os.umask(0o077)
    require(not OUT.exists(), 'Refuse to replace V24 candidate')
    report = json.loads((BASE / 'build-result.json').read_text())
    source = (BASE / 'nord3-health-stage-inert.img').read_bytes()
    require(report.get('state') == 'offline-inert-health-stage-packaged' and
            stage.sha(source) == report['image_sha256'] ==
            'c2cc903904255d7cdac00a9dd3cd60c7fde75cfe21e2dc331afafb02eb24e402',
            'V23 source differs')
    boot = read_boot_v4(source)
    primary = read_newc(decompress(boot['ramdisk']))
    old_primary = {name: dict(entry) for name, entry in primary.items()}
    old_init = primary['init']['data']
    require(old_init.endswith(OLD_TAIL) and old_init.count(OLD_TAIL) == 1,
            'V23 init handoff site differs')
    new_init = old_init[:-len(OLD_TAIL)] + NEW_TAIL
    primary['init'] = {**primary['init'], 'data': new_init}
    old_payload = source[json.loads((PORT / 'known-good-v19/recipe.json').read_text())['payload_offset']:]
    payload_len = report['supplement_bytes']
    require(stage.sha(old_payload[:payload_len]) == report['supplement_sha256'],
            'V23 supplement differs')
    supplement = read_newc(gzip.decompress(old_payload[:payload_len]))
    old_supplement = {name: dict(entry) for name, entry in supplement.items()}
    handoff = (PORT / 'autonomous-health-handoff.sh').read_bytes()
    require(handoff.startswith(b'#!/bin/sh\n'), 'Health handoff interpreter differs')
    stage.put(supplement, 'etc/lynx/autonomous-health-handoff.sh', handoff, 0o700)
    new_payload = gzip.compress(decompress(stage.packed(supplement)), compresslevel=9, mtime=0)
    require(len(new_payload) < 40_000_000, 'V24 payload exceeds exact loader bound')
    primary['etc/lynx/payload-bytes'] = {
        **primary['etc/lynx/payload-bytes'], 'data': (str(len(new_payload)) + '\n').encode()}
    primary['etc/lynx/payload-sha256'] = {
        **primary['etc/lynx/payload-sha256'], 'data': (stage.sha(new_payload) + '\n').encode()}
    ramdisk = stage.packed(primary)
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
            'V24 overlaps boot-image boundaries')
    image = bytearray(loaded.ljust(coverage, b'\0') + source[coverage:])
    image[offset:offset + max(len(new_payload), payload_len)] = new_payload.ljust(
        max(len(new_payload), payload_len), b'\0')
    image = bytes(image)
    require(len(image) == 67_108_864 and read_boot_v4(image)['kernel'] == boot['kernel'],
            'V24 kernel, header or image size differs')
    require(image[:12] == source[:12] and image[16:4096] == source[16:4096] and
            read_boot_v4(image)['cmdline'] == boot['cmdline'],
            'V24 boot header changed outside ramdisk length')
    checked_primary = read_newc(decompress(read_boot_v4(image)['ramdisk']))
    require(checked_primary['init']['data'] == new_init and
            checked_primary['etc/lynx/payload-sha256']['data'].strip().decode() == stage.sha(new_payload),
            'V24 init or payload metadata round trip differs')
    require(set(checked_primary) == set(old_primary), 'V24 primary member set differs')
    for name, entry in old_primary.items():
        if name not in ('init', 'etc/lynx/payload-bytes', 'etc/lynx/payload-sha256'):
            require(checked_primary[name] == entry, 'V24 changed unrelated primary member: ' + name)
    checked_supplement = read_newc(gzip.decompress(image[offset:offset + len(new_payload)]))
    require(checked_supplement['etc/lynx/autonomous-health-handoff.sh']['data'] == handoff,
            'V24 handoff source differs after packing')
    require(set(checked_supplement) == set(old_supplement) | {'etc/lynx/autonomous-health-handoff.sh'},
            'V24 supplement member set differs')
    for name, entry in old_supplement.items():
        require(checked_supplement[name] == entry, 'V24 changed unrelated supplement member: ' + name)
    for name in ('usr/share/lynx/health-inputs.tar.gz',
                 'usr/libexec/lynx/autonomous-health-preflight.sh',
                 'usr/libexec/lynx/autonomous-health-start.sh'):
        require(checked_supplement[name]['data'] == supplement[name]['data'],
                'V24 health input differs: ' + name)

    OUT.mkdir(mode=0o700)
    target = OUT / 'nord3-autonomous-health-untested.img'
    target.write_bytes(image)
    target.chmod(0o600)
    result = {
        'state': 'offline-autonomous-health-candidate-untested',
        'created_ns': time.time_ns(), 'image_sha256': stage.sha(image),
        'image_bytes': len(image), 'parent_v23_sha256': stage.sha(source),
        'stock_kernel_sha256': stage.sha(boot['kernel']),
        'old_init_sha256': stage.sha(old_init), 'new_init_sha256': stage.sha(new_init),
        'handoff_sha256': stage.sha(handoff), 'payload_sha256': stage.sha(new_payload),
        'payload_bytes': len(new_payload), 'auto_boot_hook_present': True,
        'hook_starts_only_after_pinned_host_confirmation': True,
        'phone_contacted': False, 'flash_performed': False,
        'inherits_private_v19_wifi_and_ssh_credentials': True, 'image_mode': '0600',
        'limits': 'Offline image layout only. No VM or handset boot of this changed init, no cold-boot module validation, no safe charging validation. SAFETY-HOLD remains active; DO NOT FLASH.'}
    (OUT / 'build-result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'state': result['state'], 'image_sha256': result['image_sha256'],
                      'result': str(OUT / 'build-result.json')}))


if __name__ == '__main__':
    main()
