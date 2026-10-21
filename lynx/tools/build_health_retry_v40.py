"""Build offline V40 with a bounded parent health-check retry and reason log."""
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
BASE = PORT / 'artifacts/delayed-health-v39-offline'
OUT = PORT / 'artifacts/health-parent-retry-v40-offline'
V39_SHA = '0eaee951ce85918f5c6c4f6f88cf79ddba40485755df730103d390025a172f49'
OLD_HANDOFF_SHA = '5e8453cb9da41f8f5391c82e20305f87f1da858d160fcac89502df976229ca4d'
MARKER = b'. /etc/lynx/wifi-runtime.sh || stop\n. /etc/lynx/wifi-local-supervise.sh || stop\n'
HANDOFF = 'etc/lynx/autonomous-health-local-handoff.sh'
sys.path.insert(0, str(PORT))
from image_formats import read_boot_v4, read_newc, require
from ramdisk_codec import decompress


def main():
    os.umask(0o077)
    require(not OUT.exists(), 'Refuse to replace V40 offline candidate')
    parent = (BASE / 'nord3-delayed-health-v39-untested.img').read_bytes()
    require(stage.sha(parent) == V39_SHA, 'V39 parent differs')
    recipe = json.loads((PORT / 'known-good-v19/recipe.json').read_text())
    coverage, offset = recipe['coverage_bytes'], recipe['payload_offset']
    boot = read_boot_v4(parent)
    primary = read_newc(decompress(boot['ramdisk']))
    old_init = primary['init']['data']
    require(old_init.count(MARKER) == 1, 'V39 init tail marker differs')
    tail = (PORT / 'lynx-v40-health-retry-tail.sh').read_bytes()
    require(tail.startswith(MARKER), 'V40 tail marker differs')
    new_init = old_init.split(MARKER)[0] + tail
    handoff = (PORT / 'autonomous-health-local-handoff-v40.sh').read_bytes()
    for name, source in [('V40 init', new_init), ('V40 handoff', handoff)]:
        require(subprocess.run(['busybox', 'sh', '-n'], input=source,
                               capture_output=True).returncode == 0,
                name + ' shell syntax failed')
    old_length = int(primary['etc/lynx/payload-bytes']['data'])
    old_payload = parent[offset:offset + old_length]
    require(stage.sha(old_payload) ==
            primary['etc/lynx/payload-sha256']['data'].decode().strip(),
            'V39 payload metadata differs')
    supplement = read_newc(gzip.decompress(old_payload))
    require(stage.sha(supplement[HANDOFF]['data']) == OLD_HANDOFF_SHA,
            'V39 local handoff differs')
    supplement[HANDOFF] = {**supplement[HANDOFF], 'data': handoff}
    payload = gzip.compress(decompress(stage.packed(supplement)),
                            compresslevel=9, mtime=0)
    require(len(payload) < 40_000_000, 'V40 payload exceeds loader bound')
    primary['init'] = {**primary['init'], 'data': new_init}
    primary['etc/lynx/payload-bytes'] = {
        **primary['etc/lynx/payload-bytes'],
        'data': (str(len(payload)) + '\n').encode()}
    primary['etc/lynx/payload-sha256'] = {
        **primary['etc/lynx/payload-sha256'],
        'data': (stage.sha(payload) + '\n').encode()}
    ramdisk = stage.packed(primary)
    header = bytearray(parent[:1584])
    struct.pack_into('<I', header, 12, len(ramdisk))
    align = lambda value: (value + 4095) // 4096 * 4096
    loaded = (bytes(header).ljust(4096, b'\0') +
              boot['kernel'].ljust(align(len(boot['kernel'])), b'\0') +
              ramdisk.ljust(align(len(ramdisk)), b'\0'))
    require(len(loaded) <= coverage <= offset and
            offset + max(old_length, len(payload)) < len(parent) - 4096,
            'V40 image sections overlap')
    image = bytearray(loaded.ljust(coverage, b'\0') + parent[coverage:])
    image[offset:offset + max(old_length, len(payload))] = payload.ljust(
        max(old_length, len(payload)), b'\0')
    image = bytes(image)
    require(len(image) == len(parent) == 67_108_864,
            'V40 image size differs')
    checked_boot = read_boot_v4(image)
    checked_primary = read_newc(decompress(checked_boot['ramdisk']))
    checked_payload = image[offset:offset + len(payload)]
    checked_supplement = read_newc(gzip.decompress(checked_payload))
    require(checked_boot['kernel'] == boot['kernel'] and
            checked_boot['cmdline'] == boot['cmdline'] and
            set(checked_primary) == set(primary) and
            all(checked_primary[name] == primary[name] for name in primary) and
            set(checked_supplement) == set(supplement) and
            all(checked_supplement[name] == supplement[name] for name in supplement) and
            image[offset + max(old_length, len(payload)):] ==
            parent[offset + max(old_length, len(payload)):],
            'V40 roundtrip or unchanged scope differs')
    OUT.mkdir(mode=0o700)
    target = OUT / 'nord3-health-parent-retry-v40-untested.img'
    target.write_bytes(image)
    target.chmod(0o600)
    (OUT / 'init-source').write_bytes(new_init)
    result = {'state': 'offline-health-parent-retry-built',
              'created_ns': time.time_ns(), 'parent_v39_sha256': V39_SHA,
              'image_sha256': stage.sha(image),
              'init_sha256': stage.sha(new_init),
              'payload_sha256': stage.sha(payload),
              'payload_bytes': len(payload),
              'health_handoff_v40_sha256': stage.sha(handoff),
              'stock_kernel_sha256': stage.sha(boot['kernel']),
              'partition_scope_if_trialled': ['boot_a'],
              'phone_contacted': False, 'flash_performed': False,
              'diagnostic_question': 'Can the V39 parent health check pass within three samples, and which failure class occurs if it cannot?',
              'observation_limit_uptime_seconds': 300,
              'outer_poweroff_seconds_after_tail': 420,
              'persistent_write_scope': '/var/log/lynx-bootdiag/<boot-id>.log on verified LYNXROOT ext4'}
    (OUT / 'build-result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'state': result['state'],
                      'result': str(OUT / 'build-result.json')}))


if __name__ == '__main__':
    main()
