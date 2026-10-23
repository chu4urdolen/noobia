"""Build an offline V47 candidate with bounded DHCP retry in the boot supplement."""

import gzip
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import time

import build_health_stage_candidate as stage


ROOT, PORT = stage.ROOT, stage.PORT
BASE = PORT / 'artifacts/persistent-alpine-v46-offline'
OUT = PORT / 'artifacts/wifi-dhcp-retry-v47-offline'
PARENT_SHA = '6c487df1c16af1717e045167c165271065e9060c5a02b16b8e1b3ce3eca28f91'
MEMBER = 'etc/lynx/wifi-runtime.sh'
OLD = b'''    $BB udhcpc -f -n -q -t 6 -T 4 -i "$wifi_interface" -x hostname:lynx -s /bin/lynx-dhcp || return 144
'''
NEW = b'''    dhcp_bound=0
    for dhcp_attempt in 1 2 3; do
        log "V47_DHCP_ATTEMPT attempt=$dhcp_attempt"
        if $BB udhcpc -f -n -q -t 6 -T 4 -i "$wifi_interface" -x hostname:lynx -s /bin/lynx-dhcp; then
            dhcp_bound=1
            break
        fi
        log "V47_DHCP_RETRY_AFTER_FAILURE attempt=$dhcp_attempt"
        [ "$dhcp_attempt" = 3 ] || $BB sleep 3
    done
    [ "$dhcp_bound" = 1 ] || return 144
'''


def main():
    from image_formats import read_boot_v4, read_newc, require
    from ramdisk_codec import decompress

    os.umask(0o077)
    require(not OUT.exists(), 'Refuse to overwrite V47 candidate')
    parent = (BASE / 'nord3-persistent-alpine-v46-untested.img').read_bytes()
    require(stage.sha(parent) == PARENT_SHA and len(parent) == 67_108_864,
            'Exact working V46 image absent')
    recipe = json.loads((PORT / 'known-good-v19/recipe.json').read_text())
    offset, coverage = recipe['payload_offset'], recipe['coverage_bytes']
    require(coverage <= offset < len(parent) - 4096, 'Payload offset outside boot image')
    boot = read_boot_v4(parent)
    primary = read_newc(decompress(boot['ramdisk']))
    size = int(primary['etc/lynx/payload-bytes']['data'].strip())
    old_payload = parent[offset:offset + size]
    require(stage.sha(old_payload) ==
            primary['etc/lynx/payload-sha256']['data'].strip().decode(),
            'V46 supplement does not match primary checksum')
    members = read_newc(gzip.decompress(old_payload))
    require(MEMBER in members, 'V46 Wi-Fi runtime member absent')
    original = members[MEMBER]['data']
    require(original.count(OLD) == 1, 'Expected unique DHCP command absent')
    changed = original.replace(OLD, NEW)
    require(subprocess.run(['busybox', 'sh', '-n'], input=changed,
                           capture_output=True).returncode == 0,
            'Modified Wi-Fi shell syntax failed')
    members[MEMBER] = {**members[MEMBER], 'data': changed}
    payload = gzip.compress(decompress(stage.packed(members)), compresslevel=9, mtime=0)
    require(offset + max(size, len(payload)) < len(parent) - 4096,
            'Updated supplement exceeds reserved boot area')
    primary['etc/lynx/payload-bytes'] = {
        **primary['etc/lynx/payload-bytes'], 'data': (str(len(payload)) + '\n').encode()}
    primary['etc/lynx/payload-sha256'] = {
        **primary['etc/lynx/payload-sha256'], 'data': (stage.sha(payload) + '\n').encode()}
    ramdisk = stage.packed(primary)
    header = bytearray(parent[:1584])
    struct.pack_into('<I', header, 12, len(ramdisk))
    align = lambda value: (value + 4095) // 4096 * 4096
    loaded = (bytes(header).ljust(4096, b'\0') +
              boot['kernel'].ljust(align(len(boot['kernel'])), b'\0') +
              ramdisk.ljust(align(len(ramdisk)), b'\0'))
    require(len(loaded) <= coverage, 'New primary overlaps signed coverage boundary')
    image = bytearray(loaded.ljust(coverage, b'\0') + parent[coverage:])
    image[offset:offset + max(size, len(payload))] = payload.ljust(
        max(size, len(payload)), b'\0')
    image = bytes(image)
    reread = read_boot_v4(image)
    reread_primary = read_newc(decompress(reread['ramdisk']))
    reread_size = int(reread_primary['etc/lynx/payload-bytes']['data'].strip())
    reread_members = read_newc(gzip.decompress(image[offset:offset + reread_size]))
    require(len(image) == len(parent) and reread['kernel'] == boot['kernel'] and
            reread['cmdline'] == boot['cmdline'] and reread_primary == primary and
            reread_size == len(payload) and
            reread_primary['init'] == read_newc(decompress(boot['ramdisk']))['init'] and
            reread_members[MEMBER]['data'] == changed and
            all(reread_members[name] == entry for name, entry in members.items()) and
            image[offset + max(size, len(payload)):] ==
            parent[offset + max(size, len(payload)):],
            'V47 roundtrip or scope check failed')
    OUT.mkdir(mode=0o700)
    target = OUT / 'nord3-wifi-dhcp-retry-v47-untested.img'
    target.write_bytes(image)
    target.chmod(0o600)
    result = {'state': 'offline-v47-dhcp-retry-candidate-built',
              'created_ns': time.time_ns(), 'parent_v46_sha256': PARENT_SHA,
              'image_sha256': stage.sha(image),
              'kernel_sha256': stage.sha(boot['kernel']),
              'init_sha256': stage.sha(primary['init']['data']),
              'old_wifi_sha256': stage.sha(original),
              'new_wifi_sha256': stage.sha(changed),
              'old_payload_sha256': stage.sha(old_payload),
              'new_payload_sha256': stage.sha(payload),
              'only_changed_supplement_member': MEMBER,
              'dhcp_attempts': 3, 'dhcp_retry_pause_seconds': 3,
              'phone_contacted': False, 'flash_performed': False,
              'hardware_trial_required': True,
              'limits': 'Offline structure and syntax validation only; no hardware trial or recovery action.'}
    (OUT / 'build-result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'state': result['state'], 'result': str(OUT / 'build-result.json')}))


if __name__ == '__main__':
    main()
