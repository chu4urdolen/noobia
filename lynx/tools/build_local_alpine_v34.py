"""Build an offline autonomous-health/persistent-Alpine V34 boot_a candidate.

V33's hardware-proven stock kernel and bootstrap stay fixed. The new tail
starts V31 health locally after Wi-Fi, then uses a local guarded PID1 handoff.
No phone contact or flash occurs.
"""
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
BASE = PORT / 'artifacts/persistent-openrc-v33-offline'
HEALTH = PORT / 'artifacts/local-health-v28-offline'
OUT = PORT / 'artifacts/local-persistent-alpine-v34-offline'
V33_SHA = '1d65456979d8a48d31de77c987b8aaf9b5ac11af62c51d00fdaff68ad47e747f'
V28_SHA = 'a22048376cec353af652c187da733eb198f1382efcf19924eebd5ba0b883d775'
MARKER = b'. /etc/lynx/wifi-runtime.sh || stop\nlynx_wifi_supervise || stop\n'
sys.path.insert(0, str(PORT))
from image_formats import read_boot_v4, read_newc, require
from ramdisk_codec import decompress


def decode(image, offset):
    boot = read_boot_v4(image)
    primary = read_newc(decompress(boot['ramdisk']))
    length = int(primary['etc/lynx/payload-bytes']['data'])
    payload = image[offset:offset + length]
    require(stage.sha(payload) == primary['etc/lynx/payload-sha256']['data'].strip().decode(),
            'Payload hash differs from primary metadata')
    return boot, primary, payload, read_newc(gzip.decompress(payload))


def main():
    os.umask(0o077)
    require(not OUT.exists(), 'Refuse to replace V34 offline candidate')
    v33 = (BASE / 'nord3-persistent-openrc-v33-untested.img').read_bytes()
    v28 = (HEALTH / 'nord3-local-health-untested.img').read_bytes()
    require(stage.sha(v33) == V33_SHA and stage.sha(v28) == V28_SHA,
            'Reviewed parent images differ')
    recipe = json.loads((PORT / 'known-good-v19/recipe.json').read_text())
    offset, coverage = recipe['payload_offset'], recipe['coverage_bytes']
    boot, primary, old_payload, supplement = decode(v33, offset)
    _, _, _, health_supplement = decode(v28, offset)
    old_primary = {name: dict(value) for name, value in primary.items()}
    old_supplement = {name: dict(value) for name, value in supplement.items()}

    old_init = primary['init']['data']
    require(old_init.count(MARKER) == 1, 'V33 init tail marker differs')
    tail = (PORT / 'lynx-v34-init-tail.sh').read_bytes()
    new_init = old_init[:old_init.index(MARKER)] + tail
    require(subprocess.run(['busybox', 'sh', '-n'], input=new_init,
                           capture_output=True).returncode == 0,
            'V34 init shell syntax failed')
    primary['init'] = {**primary['init'], 'data': new_init}

    copied_health = [
        'usr/libexec', 'usr/share', 'usr/libexec/lynx', 'usr/share/lynx',
        'usr/libexec/lynx/autonomous-health-preflight.sh',
        'usr/share/lynx/health-inputs.sha256',
        'usr/share/lynx/health-inputs.tar.gz',
    ]
    for name in copied_health:
        require(name in health_supplement and name not in supplement,
                'Health member missing or collides: ' + name)
        supplement[name] = dict(health_supplement[name])
    health_start = (PORT / 'autonomous-health-start-v31.sh').read_bytes()
    health_handoff = (PORT / 'autonomous-health-local-handoff.sh').read_bytes()
    wifi_local = (PORT / 'lynx-wifi-local-supervise-v34.sh').read_bytes()
    persistent_local = (PORT / 'persistent-openrc-handoff-v34.sh').read_bytes()
    for label, raw in [('health_start', health_start), ('health_handoff', health_handoff),
                       ('wifi_local', wifi_local), ('persistent_local', persistent_local)]:
        require(subprocess.run(['busybox', 'sh', '-n'], input=raw,
                               capture_output=True).returncode == 0,
                label + ' shell syntax failed')
    stage.put(supplement, 'usr/libexec/lynx/autonomous-health-start.sh',
              health_start, 0o700)
    stage.put(supplement, 'etc/lynx/autonomous-health-local-handoff.sh',
              health_handoff, 0o700)
    stage.put(supplement, 'etc/lynx/wifi-local-supervise.sh', wifi_local, 0o700)
    handoff_name = 'etc/lynx/persistent-openrc-handoff.sh'
    require(handoff_name in supplement and supplement[handoff_name]['data'] != persistent_local,
            'V33 persistent handoff provenance differs')
    supplement[handoff_name] = {**supplement[handoff_name], 'data': persistent_local}

    payload = gzip.compress(decompress(stage.packed(supplement)),
                            compresslevel=9, mtime=0)
    require(len(payload) < 40_000_000, 'V34 payload exceeds exact loader bound')
    primary['etc/lynx/payload-bytes'] = {
        **primary['etc/lynx/payload-bytes'], 'data': (str(len(payload)) + '\n').encode()}
    primary['etc/lynx/payload-sha256'] = {
        **primary['etc/lynx/payload-sha256'], 'data': (stage.sha(payload) + '\n').encode()}
    ramdisk = stage.packed(primary)
    header = bytearray(v33[:1584])
    struct.pack_into('<I', header, 12, len(ramdisk))
    align = lambda value: (value + 4095) // 4096 * 4096
    loaded = (bytes(header).ljust(4096, b'\0') +
              boot['kernel'].ljust(align(len(boot['kernel'])), b'\0') +
              ramdisk.ljust(align(len(ramdisk)), b'\0'))
    require(len(loaded) <= coverage <= offset and
            offset + max(len(old_payload), len(payload)) < len(v33) - 4096,
            'V34 overlaps boot image boundaries')
    image = bytearray(loaded.ljust(coverage, b'\0') + v33[coverage:])
    image[offset:offset + max(len(old_payload), len(payload))] = payload.ljust(
        max(len(old_payload), len(payload)), b'\0')
    image = bytes(image)
    checked_boot, checked_primary, checked_payload, checked_supplement = decode(image, offset)
    require(len(image) == len(v33) == 67_108_864 and
            checked_boot['kernel'] == boot['kernel'] and
            checked_boot['cmdline'] == boot['cmdline'] and
            image[:12] == v33[:12] and image[16:4096] == v33[16:4096],
            'V34 stock kernel, cmdline or header differs')
    require(set(checked_primary) == set(old_primary) and
            checked_primary['init']['data'] == new_init,
            'V34 primary member set or init roundtrip differs')
    for name, entry in old_primary.items():
        if name not in ('init', 'etc/lynx/payload-bytes', 'etc/lynx/payload-sha256'):
            require(checked_primary[name] == entry,
                    'V34 changed unrelated primary member: ' + name)
    expected_supplement = set(old_supplement) | set(copied_health) | {
        'usr/libexec/lynx/autonomous-health-start.sh',
        'etc/lynx/autonomous-health-local-handoff.sh',
        'etc/lynx/wifi-local-supervise.sh'}
    require(set(checked_supplement) == expected_supplement,
            'V34 supplement member set differs')
    for name, entry in old_supplement.items():
        if name != handoff_name:
            require(checked_supplement[name] == entry,
                    'V34 changed unrelated supplement member: ' + name)
    for name, entry in supplement.items():
        require(checked_supplement[name] == entry,
                'V34 supplement roundtrip differs: ' + name)
    require(stage.sha(checked_payload) == stage.sha(payload),
            'V34 payload roundtrip differs')

    OUT.mkdir(mode=0o700)
    target = OUT / 'nord3-local-persistent-alpine-v34-untested.img'
    target.write_bytes(image)
    target.chmod(0o600)
    (OUT / 'init-source').write_bytes(new_init)
    report = {'state': 'offline-autonomous-alpine-candidate-built',
              'created_ns': time.time_ns(), 'parent_v33_sha256': V33_SHA,
              'health_reference_v28_sha256': V28_SHA,
              'image_sha256': stage.sha(image), 'image_bytes': len(image),
              'stock_kernel_sha256': stage.sha(boot['kernel']),
              'init_sha256': stage.sha(new_init),
              'payload_sha256': stage.sha(payload), 'payload_bytes': len(payload),
              'health_start_v31_sha256': stage.sha(health_start),
              'health_inputs_sha256': stage.sha(
                  checked_supplement['usr/share/lynx/health-inputs.tar.gz']['data']),
              'phone_contacted': False, 'flash_performed': False,
              'known_limit': 'Autonomous Wi-Fi/health and local Alpine handoff are untested together on Lynx; charging remains unvalidated.'}
    (OUT / 'build-result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'state': report['state'], 'result': str(OUT / 'build-result.json')}))


if __name__ == '__main__':
    main()
