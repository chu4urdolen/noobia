"""Measure an inert OpenRC rootfs addition against V19's bounded boot payload."""
import gzip
import hashlib
import json
import stat
import time
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'linux-port'))
from image_formats import read_newc, require
from prepare_busybox_diagnostics import pack
from ramdisk_codec import decompress

BASE = ROOT / 'linux-port/artifacts/busybox-wifi-ssh-twostage-v19'
EXPORT = ROOT / 'linux-port/artifacts/openrc-rootfs-export'
OUTPUT = EXPORT / 'payload-fit.json'
MAX_PAYLOAD = 40_000_000  # The V19 init refuses bytes >= 40,000,000.
PARTITION_BYTES = 64 * 1024 * 1024
PAYLOAD_OFFSET = 24 * 1024 * 1024


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    validation = json.loads((BASE / 'build-validation.json').read_text())
    old_payload = (BASE / 'supplement.cpio.gz').read_bytes()
    rootfs_path = EXPORT / 'alpine-openrc-rootfs.cpio.gz'
    rootfs = rootfs_path.read_bytes()
    manifest = json.loads((EXPORT / 'manifest.json').read_text())
    require(sha(old_payload) == validation['supplement_sha256'], 'V19 supplement hash changed')
    require(sha(rootfs) == manifest['archive_sha256'], 'OpenRC rootfs hash changed')
    entries = read_newc(gzip.decompress(old_payload))
    target = 'usr/share/lynx/alpine-openrc-rootfs.cpio.gz'
    require(target not in entries, 'OpenRC rootfs payload already exists in V19 supplement')
    for name in ('usr/share', 'usr/share/lynx'):
        if name not in entries:
            entries[name] = {'mode': stat.S_IFDIR | 0o755, 'uid': 0, 'gid': 0,
                             'rdevmajor': 0, 'rdevminor': 0, 'data': b''}
        require(stat.S_ISDIR(entries[name]['mode']), 'Payload parent is not a directory: ' + name)
    entries[target] = {'mode': stat.S_IFREG | 0o644, 'uid': 0, 'gid': 0,
                       'rdevmajor': 0, 'rdevminor': 0, 'data': rootfs}
    raw = decompress(pack(dict(sorted(entries.items(), key=lambda pair: (
        not stat.S_ISDIR(pair[1]['mode']), pair[0].count('/'), pair[0])))))
    require(read_newc(raw) == entries, 'Combined V19 supplement CPIO round trip differs')
    combined = gzip.compress(raw, compresslevel=9, mtime=0)
    available_by_partition = PARTITION_BYTES - PAYLOAD_OFFSET
    report = {
        'state': 'openrc-payload-fit-measured', 'created_ns': time.time_ns(),
        'v19_image_sha256': validation['candidate_sha256'],
        'v19_supplement_sha256': sha(old_payload), 'v19_supplement_bytes': len(old_payload),
        'openrc_rootfs_sha256': sha(rootfs), 'openrc_rootfs_bytes': len(rootfs),
        'combined_supplement_sha256': sha(combined),
        'combined_supplement_bytes': len(combined),
        'init_runtime_limit_bytes_exclusive': MAX_PAYLOAD,
        'boot_a_partition_bytes': PARTITION_BYTES,
        'supplement_offset_bytes': PAYLOAD_OFFSET,
        'partition_space_after_offset_bytes': available_by_partition,
        'remaining_bytes_under_init_limit': MAX_PAYLOAD - len(combined),
        'fits_v19_payload_limit': len(combined) < MAX_PAYLOAD,
        'fits_boot_a_space_after_offset': len(combined) <= available_by_partition,
        'payload_path_if_integrated': target,
        'embedded_but_not_extracted_or_launched': True,
        'phone_contacted': False, 'phone_boot_or_partition_changed': False,
        'limits': 'Size calculation only. No boot image candidate was built, no phone test occurred, and the OpenRC root is inert unless a later init explicitly extracts and hands off to it.',
    }
    OUTPUT.write_text(json.dumps(report, indent=2) + '\n')
    require(report['fits_v19_payload_limit'] and report['fits_boot_a_space_after_offset'],
            'Combined rootfs exceeds the V19 payload capacity')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
