"""Build an offline V19-derived, host-armed persistent Alpine PID 1 candidate.

The image contains no Alpine root archive: it uses Lynx's verified ext4 root.
No handset contact or flash occurs. Keep the private image mode 0600.
"""
import gzip
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
BASE = PORT / 'artifacts/busybox-wifi-ssh-twostage-v19'
OUT = PORT / 'artifacts/persistent-openrc-v29-offline'
sys.path.insert(0, str(PORT))
from image_formats import read_boot_v4, read_newc, require
from prepare_busybox_diagnostics import pack
from ramdisk_codec import decompress


def sha(data):
    return hashlib.sha256(data).hexdigest()


def put(entries, name, data):
    require(name not in entries, 'Refuse to replace V19 member: ' + name)
    parts = Path(name).parts
    for index in range(1, len(parts)):
        parent = '/'.join(parts[:index])
        if parent not in entries:
            entries[parent] = {'mode': stat.S_IFDIR | 0o755, 'uid': 0, 'gid': 0,
                               'rdevmajor': 0, 'rdevminor': 0, 'data': b''}
        require(stat.S_ISDIR(entries[parent]['mode']), 'Non-directory parent: ' + parent)
    entries[name] = {'mode': stat.S_IFREG | 0o755, 'uid': 0, 'gid': 0,
                     'rdevmajor': 0, 'rdevminor': 0, 'data': data}


def main():
    os.umask(0o077)
    require(not OUT.exists(), 'Refuse to replace an existing V29 candidate')
    build = json.loads((BASE / 'build-validation.json').read_text())
    source = (BASE / 'nord3-busybox-candidate.img').read_bytes()
    require(sha(source) == build['candidate_sha256'] ==
            '5ce2dbf8a7c132fa7e31f6be70aa76f83afe8c293e2cd5f02251a532486fd851',
            'Frozen V19 image differs')
    old_payload = (BASE / 'supplement.cpio.gz').read_bytes()
    require(sha(old_payload) == build['supplement_sha256'], 'V19 supplement differs')
    recipe = json.loads((PORT / 'known-good-v19/recipe.json').read_text())
    offset = recipe['payload_offset']
    require(source[offset:offset + len(old_payload)] == old_payload,
            'V19 inline supplement differs from its saved source')
    boot = read_boot_v4(source)
    primary = read_newc(decompress(boot['ramdisk']))
    supplement = read_newc(gzip.decompress(old_payload))
    old_primary = {name: dict(entry) for name, entry in primary.items()}
    old_supplement = {name: dict(entry) for name, entry in supplement.items()}
    added = {
        'etc/lynx/openrc-handoff-guard.sh': (PORT / 'openrc-handoff-guard.sh').read_bytes(),
        'etc/lynx/persistent-openrc-handoff.sh': (PORT / 'persistent-openrc-handoff.sh').read_bytes(),
    }
    for name, data in added.items():
        require(data.startswith(b'#!/bin/sh\n'), 'Handoff script interpreter differs')
        put(supplement, name, data)
    packed_supplement = pack(dict(sorted(supplement.items(), key=lambda pair: (
        not stat.S_ISDIR(pair[1]['mode']), pair[0].count('/'), pair[0]))))
    new_payload = gzip.compress(decompress(packed_supplement), compresslevel=9, mtime=0)
    require(len(new_payload) < 40_000_000, 'V29 payload exceeds V19 loader bound')

    old_tail = (b"lynx_wifi_supervise\n"
                b"log 'WIFI_SUPERVISOR_FINISHED; PID1_REMAINS_ALIVE'\n"
                b"stop\n")
    init = primary['init']['data']
    require(init.endswith(old_tail) and init.count(old_tail) == 1,
            'V19 init tail differs')
    new_tail = (b"lynx_wifi_supervise || stop\n"
                b"log 'PINNED_SSH_CONFIRMED; PERSISTENT_OPENRC_WAIT'\n"
                b". /etc/lynx/persistent-openrc-handoff.sh || { log 'PERSISTENT_OPENRC_SCRIPT_LOAD_FAILED'; stop; }\n"
                b"lynx_persistent_openrc_wait_and_handoff || log 'PERSISTENT_OPENRC_REFUSED; BUSYBOX_RESCUE_ACTIVE'\n"
                b"stop\n")
    primary['init'] = {**primary['init'], 'data': init[:-len(old_tail)] + new_tail}
    primary['etc/lynx/payload-bytes'] = {
        **primary['etc/lynx/payload-bytes'], 'data': (str(len(new_payload)) + '\n').encode()}
    primary['etc/lynx/payload-sha256'] = {
        **primary['etc/lynx/payload-sha256'], 'data': (sha(new_payload) + '\n').encode()}
    ramdisk = pack(dict(sorted(primary.items(), key=lambda pair: (
        not stat.S_ISDIR(pair[1]['mode']), pair[0].count('/'), pair[0]))))
    header = bytearray(source[:1584])
    struct.pack_into('<I', header, 12, len(ramdisk))
    align = lambda value: (value + 4095) // 4096 * 4096
    loaded = (bytes(header).ljust(4096, b'\0') +
              boot['kernel'].ljust(align(len(boot['kernel'])), b'\0') +
              ramdisk.ljust(align(len(ramdisk)), b'\0'))
    coverage = recipe['coverage_bytes']
    require(len(loaded) <= coverage <= offset and
            offset + max(len(new_payload), len(old_payload)) < len(source) - 4096,
            'V29 overlaps boot image boundaries')
    candidate = bytearray(loaded.ljust(coverage, b'\0') + source[coverage:])
    candidate[offset:offset + max(len(new_payload), len(old_payload))] = new_payload.ljust(
        max(len(new_payload), len(old_payload)), b'\0')
    candidate = bytes(candidate)
    require(len(candidate) == len(source) == 67_108_864, 'V29 image size differs')
    checked_boot = read_boot_v4(candidate)
    require(checked_boot['kernel'] == boot['kernel'] and
            checked_boot['cmdline'] == boot['cmdline'], 'Stock kernel/cmdline changed')
    require(candidate[:12] == source[:12] and candidate[16:4096] == source[16:4096],
            'Boot header changed outside ramdisk length')
    checked_primary = read_newc(decompress(checked_boot['ramdisk']))
    checked_supplement = read_newc(gzip.decompress(candidate[offset:offset + len(new_payload)]))
    require(set(checked_primary) == set(old_primary), 'Primary member set differs')
    require(set(checked_supplement) == set(old_supplement) | set(added),
            'Supplement member set differs')
    for name, entry in old_primary.items():
        if name not in ('init', 'etc/lynx/payload-bytes', 'etc/lynx/payload-sha256'):
            require(checked_primary[name] == entry, 'Unrelated primary member changed: ' + name)
    for name, entry in old_supplement.items():
        require(checked_supplement[name] == entry, 'Unrelated supplement member changed: ' + name)
    for name, data in added.items():
        require(checked_supplement[name]['data'] == data, 'Handoff script roundtrip differs')
    require(checked_primary['init']['data'] == primary['init']['data'], 'Init roundtrip differs')

    OUT.mkdir(mode=0o700)
    image_path = OUT / 'nord3-persistent-openrc-untested.img'
    image_path.write_bytes(candidate)
    image_path.chmod(0o600)
    (OUT / 'init-source').write_bytes(primary['init']['data'])
    (OUT / 'supplement.cpio.gz').write_bytes(new_payload)
    result = {
        'state': 'offline-persistent-openrc-candidate-built',
        'created_ns': time.time_ns(), 'image_sha256': sha(candidate),
        'image_bytes': len(candidate), 'parent_v19_sha256': build['candidate_sha256'],
        'stock_kernel_sha256': sha(boot['kernel']),
        'init_sha256': sha(primary['init']['data']),
        'payload_sha256': sha(new_payload), 'payload_bytes': len(new_payload),
        'script_sha256': {name: sha(data) for name, data in added.items()},
        'phone_contacted': False, 'flash_performed': False,
        'inherits_private_v19_wifi_and_ssh_credentials': True,
        'limitations': 'Offline, untested boot image. Requires pinned host SSH and a separate arm token after live health checks. No autonomous Alpine boot or safe charging proof. Preserve V19 and stock undo; do not flash without a fresh recovery preflight.'}
    (OUT / 'build-result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'state': result['state'], 'result': str(OUT / 'build-result.json')}))


if __name__ == '__main__':
    main()
