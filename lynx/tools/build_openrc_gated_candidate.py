"""Build a local-only V21 image: V19 plus a bounded OpenRC handoff.

This never contacts or flashes Lynx. The resulting image inherits private Wi-Fi
and SSH credentials from V19 and must remain local with mode 0600.
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
BASE = PORT / 'artifacts/busybox-wifi-ssh-twostage-v19'
EXPORT = PORT / 'artifacts/openrc-rootfs-export'
OUT = PORT / 'artifacts/openrc-gated-v21-fastboot-timeout'
sys.path.insert(0, str(PORT))
from image_formats import read_boot_v4, read_newc, require
from prepare_busybox_diagnostics import pack
from ramdisk_codec import decompress


def sha(data):
    return hashlib.sha256(data).hexdigest()


def put(entries, name, data, mode=stat.S_IFREG | 0o644):
    parts = Path(name).parts
    for index in range(1, len(parts)):
        parent = '/'.join(parts[:index])
        if parent not in entries:
            entries[parent] = {'mode': stat.S_IFDIR | 0o755, 'uid': 0, 'gid': 0,
                               'rdevmajor': 0, 'rdevminor': 0, 'data': b''}
        require(stat.S_ISDIR(entries[parent]['mode']), 'Non-directory parent: ' + parent)
    entries[name] = {'mode': mode, 'uid': 0, 'gid': 0,
                     'rdevmajor': 0, 'rdevminor': 0, 'data': data}


def main():
    os.umask(0o077)
    require(not OUT.exists(), 'Refuse to replace an existing candidate directory')
    build = json.loads((BASE / 'build-validation.json').read_text())
    raw = (BASE / 'nord3-busybox-candidate.img').read_bytes()
    require(sha(raw) == build['candidate_sha256'] and build['candidate_sha256'] ==
            '5ce2dbf8a7c132fa7e31f6be70aa76f83afe8c293e2cd5f02251a532486fd851',
            'V19 differs from the frozen hardware-proven baseline')
    payload_old = (BASE / 'supplement.cpio.gz').read_bytes()
    require(sha(payload_old) == build['supplement_sha256'], 'V19 payload hash differs')
    rootfs = (EXPORT / 'alpine-openrc-rootfs.cpio.gz').read_bytes()
    root_manifest = json.loads((EXPORT / 'manifest.json').read_text())
    require(sha(rootfs) == root_manifest['archive_sha256'], 'OpenRC rootfs export hash differs')

    boot = read_boot_v4(raw)
    primary = read_newc(decompress(boot['ramdisk']))
    supplement = read_newc(gzip.decompress(payload_old))
    target = 'usr/share/lynx/alpine-openrc-rootfs.cpio.gz'
    require(target not in supplement, 'OpenRC rootfs already exists in V19 payload')
    put(supplement, target, rootfs)
    put(supplement, 'usr/share/lynx/alpine-openrc-rootfs.sha256',
        (root_manifest['archive_sha256'] + '\n').encode())
    put(supplement, 'etc/lynx/openrc-handoff-guard.sh',
        (PORT / 'openrc-handoff-guard.sh').read_bytes(), stat.S_IFREG | 0o100755)
    put(supplement, 'etc/lynx/openrc-handoff.sh',
        (PORT / 'openrc-handoff.sh').read_bytes(), stat.S_IFREG | 0o100755)
    payload_new = gzip.compress(decompress(pack(dict(sorted(supplement.items(), key=lambda pair: (
        not stat.S_ISDIR(pair[1]['mode']), pair[0].count('/'), pair[0]))))),
        compresslevel=9, mtime=0)
    max_payload = 40_000_000
    require(len(payload_new) < max_payload, 'OpenRC payload exceeds V19 init size limit')
    put(primary, 'etc/lynx/payload-bytes', (str(len(payload_new)) + '\n').encode())
    put(primary, 'etc/lynx/payload-sha256', (sha(payload_new) + '\n').encode())
    init = primary['init']['data']
    old_tail = b'lynx_wifi_supervise\nlog \'WIFI_SUPERVISOR_FINISHED; PID1_REMAINS_ALIVE\'\nstop\n'
    require(init.endswith(old_tail), 'V19 init tail differs from the expected exact source')
    new_tail = (b"lynx_wifi_supervise || stop\n"
                b"log 'WIFI_SUPERVISOR_FINISHED; CHECKING_OPT_IN_OPENRC_GATE'\n"
                b". /etc/lynx/openrc-handoff.sh || { log 'OPENRC_SCRIPT_LOAD_FAILED; REQUESTING_FASTBOOT'; /bin/boot-proof-reboot; stop; }\n"
                b"lynx_openrc_handoff\n"
                b"log 'OPENRC_HANDOFF_FAILED; REQUESTING_FASTBOOT'\n"
                b"/bin/boot-proof-reboot\n"
                b"stop\n")
    primary['init']['data'] = init[:-len(old_tail)] + new_tail
    ramdisk = pack(primary)

    recipe = json.loads((PORT / 'known-good-v19/recipe.json').read_text())
    header = bytearray(raw[:1584])
    struct.pack_into('<I', header, 12, len(ramdisk))
    align = lambda value: (value + 4095) // 4096 * 4096
    loaded = (bytes(header).ljust(4096, b'\0') + boot['kernel'].ljust(align(len(boot['kernel'])), b'\0') +
              ramdisk.ljust(align(len(ramdisk)), b'\0'))
    coverage = recipe['coverage_bytes']
    require(len(loaded) <= coverage, 'New ramdisk overlaps boot metadata')
    image = bytearray(loaded.ljust(coverage, b'\0') + raw[coverage:])
    offset = recipe['payload_offset']
    require(coverage <= offset and offset + len(payload_new) < len(image) - 4096,
            'New supplement exceeds boot_a payload capacity')
    image[offset:offset + max(len(payload_new), len(payload_old))] = payload_new.ljust(
        max(len(payload_new), len(payload_old)), b'\0')
    image = bytes(image)
    OUT.mkdir(mode=0o700)
    candidate = OUT / 'nord3-openrc-gated-candidate.img'
    candidate.write_bytes(image)
    candidate.chmod(0o600)
    (OUT / 'init-source').write_bytes(primary['init']['data'])
    (OUT / 'init-source').chmod(0o600)
    (OUT / 'supplement.cpio.gz').write_bytes(payload_new)
    (OUT / 'supplement.cpio.gz').chmod(0o600)
    report = {
        'state': 'offline-openrc-gated-candidate-built', 'created_ns': time.time_ns(),
        'candidate_sha256': sha(image), 'candidate_bytes': len(image),
        'init_sha256': sha(primary['init']['data']),
        'parent_v19_sha256': build['candidate_sha256'], 'payload_sha256': sha(payload_new),
        'payload_bytes': len(payload_new), 'payload_limit_exclusive': max_payload,
        'openrc_rootfs_sha256': root_manifest['archive_sha256'],
        'handoff_guard_sha256': sha((PORT / 'openrc-handoff-guard.sh').read_bytes()),
        'handoff_script_sha256': sha((PORT / 'openrc-handoff.sh').read_bytes()),
        'flash_performed': False, 'phone_contacted': False,
        'inherits_private_v19_wifi_and_ssh_credentials': True,
        'candidate_mode': '0600',
        'limitations': 'Offline candidate only. No fresh-boot phone proof or real-device OpenRC PID 1 handoff. Missing/failed gate returns to Fastboot after at most 180 seconds following pinned contact. Host installs and verifies RAM-only thermal/battery watchers; OpenRC does not yet manage Wi-Fi/SSH services. No flash authorization is implied.'
    }
    (OUT / 'build-result.json').write_text(json.dumps(report, indent=2) + '\n')
    (OUT / 'build-result.json').chmod(0o600)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
