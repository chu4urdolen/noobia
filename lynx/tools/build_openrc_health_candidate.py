"""Build an offline V22 candidate by adding the verified health OpenRC root.

This only replaces V21's nested Alpine/OpenRC root archive and the payload
length/hash metadata. It inherits V19's private Wi-Fi and SSH credentials.
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
BASE = PORT / 'artifacts/openrc-gated-v21-fastboot-timeout'
HEALTH = PORT / 'artifacts/openrc-health-rootfs-export'
OUT = PORT / 'artifacts/openrc-health-v22-offline'
sys.path.insert(0, str(PORT))
from image_formats import read_boot_v4, read_newc, require
from prepare_busybox_diagnostics import pack
from ramdisk_codec import decompress


def sha(data):
    return hashlib.sha256(data).hexdigest()


def packed(entries):
    ordered = dict(sorted(entries.items(), key=lambda pair: (
        not stat.S_ISDIR(pair[1]['mode']), pair[0].count('/'), pair[0])))
    return pack(ordered)


def replace_file(entries, name, data):
    require(name in entries and stat.S_ISREG(entries[name]['mode']), 'Missing regular member ' + name)
    entries[name] = {**entries[name], 'data': data}


def main():
    os.umask(0o077)
    require(not OUT.exists(), 'Refuse to replace a V22 candidate')
    v21 = json.loads((BASE / 'build-result.json').read_text())
    source = (BASE / 'nord3-openrc-gated-candidate.img').read_bytes()
    require(v21.get('state') == 'offline-openrc-gated-candidate-built' and
            sha(source) == v21.get('candidate_sha256') ==
            '23fec5b5f319dfcd5bf8555478f843cd7bb9be3a902afc8061ea09c8a0457e4f',
            'V21 base image differs from reviewed source')
    old_payload = (BASE / 'supplement.cpio.gz').read_bytes()
    require(sha(old_payload) == v21['payload_sha256'], 'V21 payload differs')
    health_manifest = json.loads((HEALTH / 'manifest.json').read_text())
    health_root = (HEALTH / 'alpine-openrc-health-rootfs.cpio.gz').read_bytes()
    require(health_manifest.get('state') == 'verified-openrc-health-rootfs-payload' and
            health_manifest.get('roundtrip_verified') and
            sha(health_root) == health_manifest.get('archive_sha256'),
            'Health OpenRC root archive differs')
    root_entries = read_newc(gzip.decompress(health_root))
    for name in ('usr/libexec/lynx-health-supervisor.sh', 'etc/init.d/lynx-health',
                 'etc/runlevels/default/lynx-health'):
        require(name in root_entries, 'Missing health root member ' + name)

    boot = read_boot_v4(source)
    primary = read_newc(decompress(boot['ramdisk']))
    require(sha(primary['init']['data']) == v21['init_sha256'], 'V21 init differs')
    supplement = read_newc(gzip.decompress(old_payload))
    target = 'usr/share/lynx/alpine-openrc-rootfs.cpio.gz'
    old_root = supplement[target]['data']
    require(sha(old_root) == v21['openrc_rootfs_sha256'], 'V21 nested root differs')
    replace_file(supplement, target, health_root)
    replace_file(supplement, 'usr/share/lynx/alpine-openrc-rootfs.sha256',
                 (sha(health_root) + '\n').encode())
    new_payload = gzip.compress(decompress(packed(supplement)), compresslevel=9, mtime=0)
    require(len(new_payload) < 40_000_000, 'V22 payload exceeds exact V19 loader bound')
    replace_file(primary, 'etc/lynx/payload-bytes', (str(len(new_payload)) + '\n').encode())
    replace_file(primary, 'etc/lynx/payload-sha256', (sha(new_payload) + '\n').encode())
    ramdisk = packed(primary)

    recipe = json.loads((PORT / 'known-good-v19/recipe.json').read_text())
    header = bytearray(source[:1584])
    struct.pack_into('<I', header, 12, len(ramdisk))
    align = lambda value: (value + 4095) // 4096 * 4096
    loaded = (bytes(header).ljust(4096, b'\0') +
              boot['kernel'].ljust(align(len(boot['kernel'])), b'\0') +
              ramdisk.ljust(align(len(ramdisk)), b'\0'))
    coverage = recipe['coverage_bytes']
    offset = recipe['payload_offset']
    require(len(loaded) <= coverage and coverage <= offset and
            offset + len(new_payload) < len(source) - 4096,
            'V22 metadata/payload would overlap boot image boundaries')
    image = bytearray(loaded.ljust(coverage, b'\0') + source[coverage:])
    image[offset:offset + max(len(new_payload), len(old_payload))] = new_payload.ljust(
        max(len(new_payload), len(old_payload)), b'\0')
    image = bytes(image)
    require(len(image) == 67_108_864 and read_boot_v4(image)['kernel'] == boot['kernel'],
            'V22 boot header or stock kernel differs')
    check_primary = read_newc(decompress(read_boot_v4(image)['ramdisk']))
    require(check_primary['init']['data'] == primary['init']['data'] and
            check_primary['etc/lynx/payload-sha256']['data'].strip().decode() == sha(new_payload),
            'V22 primary init/payload metadata round trip differs')
    check_supplement = read_newc(gzip.decompress(image[offset:offset + len(new_payload)]))
    require(check_supplement[target]['data'] == health_root,
            'V22 nested OpenRC health root round trip differs')

    OUT.mkdir(mode=0o700)
    candidate = OUT / 'nord3-openrc-health-candidate.img'
    candidate.write_bytes(image)
    candidate.chmod(0o600)
    (OUT / 'supplement.cpio.gz').write_bytes(new_payload)
    (OUT / 'supplement.cpio.gz').chmod(0o600)
    report = {
        'state': 'offline-openrc-health-candidate-built', 'created_ns': time.time_ns(),
        'candidate_sha256': sha(image), 'candidate_bytes': len(image),
        'parent_v21_sha256': v21['candidate_sha256'],
        'parent_v19_sha256': v21['parent_v19_sha256'],
        'stock_kernel_sha256': sha(boot['kernel']), 'init_sha256': sha(primary['init']['data']),
        'payload_sha256': sha(new_payload), 'payload_bytes': len(new_payload),
        'nested_health_root_sha256': sha(health_root),
        'health_supervisor_sha256': health_manifest['supervisor_sha256'],
        'health_service_sha256': health_manifest['service_sha256'],
        'flash_performed': False, 'phone_contacted': False,
        'inherits_private_v19_wifi_and_ssh_credentials': True,
        'candidate_mode': '0600',
        'limits': 'Offline image only. V21 still requires host-assisted sensor, gauge and watcher startup before OpenRC handoff. No V22 handset trial, thermal-hold clearance or flash authorization is implied.'
    }
    (OUT / 'build-result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'state': report['state'], 'candidate_sha256': report['candidate_sha256'],
                      'result': str(OUT / 'build-result.json')}))


if __name__ == '__main__':
    main()
