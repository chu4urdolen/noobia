"""Export a verified Alpine/OpenRC runtime as a deterministic cpio.gz payload."""
import argparse
import gzip
import hashlib
import json
import os
import stat
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'linux-port'))
from image_formats import read_newc, require
from prepare_busybox_diagnostics import pack
from ramdisk_codec import decompress

REPLAY = ROOT / 'linux-port/artifacts/openrc-bundle-replay-1792236671965134306/result.json'
HANDOFF = ROOT / 'linux-port/artifacts/busybox-wifi-ssh-twostage-v19/nord3-busybox-candidate.img'
HANDOFF_SHA256 = '5ce2dbf8a7c132fa7e31f6be70aa76f83afe8c293e2cd5f02251a532486fd851'
OUT = ROOT / 'linux-port/artifacts/openrc-rootfs-export'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def verified_source():
    replay = json.loads(REPLAY.read_text())
    require(replay.get('state') == 'offline-openrc-replay-verified', 'OpenRC replay is not verified')
    require(replay.get('phone_contacted') is False and
            replay.get('phone_boot_or_partition_changed') is False,
            'Replay unexpectedly contacted or changed the phone')
    require(all(item.get('output', '').endswith(': OK')
                for item in replay.get('package_signatures', [])),
            'An OpenRC APK signature did not verify')
    runtime = Path(replay['runtime_root']).resolve(strict=True)
    require(runtime.parent.name.startswith('openrc-bundle-replay-'),
            'Runtime root is outside the verified replay artifact')
    require(sha(HANDOFF.read_bytes()) == HANDOFF_SHA256,
            'Frozen V19 baseline hash changed')
    for name in ('bin/busybox', 'lib/ld-musl-aarch64.so.1', 'sbin/openrc-init',
                 'sbin/openrc-shutdown', 'etc/alpine-release', 'etc/apk/keys'):
        require((runtime / name).exists(), 'OpenRC runtime lacks ' + name)
    return replay, runtime


def build():
    replay, runtime = verified_source()
    entries = {}
    regular_bytes = 0
    skipped_cache_files = 0
    for path in sorted(runtime.rglob('*')):
        rel = path.relative_to(runtime).as_posix()
        if rel.startswith('var/cache/apk/'):
            skipped_cache_files += 1
            continue
        info = path.lstat()
        mode = info.st_mode
        if stat.S_ISDIR(mode):
            data, cpio_mode = b'', stat.S_IFDIR | stat.S_IMODE(mode)
        elif stat.S_ISREG(mode):
            data, cpio_mode = path.read_bytes(), stat.S_IFREG | stat.S_IMODE(mode)
            regular_bytes += len(data)
        elif stat.S_ISLNK(mode):
            data, cpio_mode = os.readlink(path).encode(), stat.S_IFLNK | stat.S_IMODE(mode)
        else:
            raise ValueError('Unsupported OpenRC rootfs member: ' + rel)
        entries[rel] = {'mode': cpio_mode, 'uid': 0, 'gid': 0,
                        'rdevmajor': 0, 'rdevminor': 0, 'data': data}
    require(all(name in entries for name in
                ('bin/busybox', 'lib/ld-musl-aarch64.so.1', 'sbin/openrc-init')),
            'Exported runtime lacks boot-critical files')
    raw_cpio = decompress(pack(dict(sorted(entries.items(), key=lambda pair: (
        not stat.S_ISDIR(pair[1]['mode']), pair[0].count('/'), pair[0])))))
    require(read_newc(raw_cpio) == entries, 'Rootfs CPIO round trip differs')
    archive = gzip.compress(raw_cpio, compresslevel=9, mtime=0)
    require(len(archive) <= 24 * 1024 * 1024,
            'Rootfs payload exceeds the offline packaging budget')
    return replay, entries, regular_bytes, skipped_cache_files, archive


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify-existing', action='store_true')
    args = parser.parse_args()
    replay, entries, regular_bytes, skipped, archive = build()
    digest = sha(archive)
    if args.verify_existing:
        manifest = json.loads((OUT / 'manifest.json').read_text())
        existing = (OUT / 'alpine-openrc-rootfs.cpio.gz').read_bytes()
        require(manifest.get('state') == 'verified-openrc-rootfs-payload' and
                manifest.get('archive_sha256') == digest and existing == archive,
                'Existing OpenRC rootfs payload differs from deterministic rebuild')
        print(json.dumps({'state': 'openrc-rootfs-export-verified',
                          'archive_sha256': digest, 'bytes': len(archive)}))
        return
    require(not OUT.exists(), 'Preserve the existing exported OpenRC payload')
    OUT.mkdir(mode=0o700)
    payload = OUT / 'alpine-openrc-rootfs.cpio.gz'
    payload.write_bytes(archive)
    payload.chmod(0o600)
    manifest = {
        'state': 'verified-openrc-rootfs-payload',
        'created_ns': time.time_ns(),
        'archive': str(payload), 'archive_sha256': digest,
        'archive_bytes': len(archive), 'uncompressed_cpio_bytes': len(decompress(pack(entries))),
        'entry_count': len(entries), 'regular_file_bytes': regular_bytes,
        'omitted_apk_cache_member_count': skipped,
        'alpine_release': (Path(replay['runtime_root']) / 'etc/alpine-release').read_text().strip(),
        'openrc_replay_receipt': str(REPLAY),
        'openrc_bundle_sha256': replay['bundle_sha256'],
        'base_rootfs_sha256': replay['base_rootfs_sha256'],
        'stock_kernel_sha256': 'cbc9f5dc54b5198ddd1e82d5d7bde96f43cbb383a663726ddd68919b0639d3af',
        'v19_image_sha256': HANDOFF_SHA256,
        'phone_contacted': False, 'phone_boot_or_partition_changed': False,
        'limits': 'Offline rootfs payload only; it is not incorporated in a handset image or tested on Lynx.',
    }
    (OUT / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps({'state': manifest['state'], 'archive': str(payload),
                      'archive_sha256': digest, 'archive_bytes': len(archive),
                      'entry_count': len(entries), 'regular_file_bytes': regular_bytes}))


if __name__ == '__main__':
    main()
