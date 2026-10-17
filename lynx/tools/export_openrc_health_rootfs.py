"""Add Lynx's health supervisor and OpenRC service to the verified RAM root."""
import gzip
import hashlib
import json
import os
import stat
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PORT = ROOT / 'linux-port'
SOURCE = PORT / 'artifacts/openrc-rootfs-export'
OUT = PORT / 'artifacts/openrc-health-rootfs-export'
sys.path.insert(0, str(PORT))
from image_formats import read_newc, require
from prepare_busybox_diagnostics import pack
from ramdisk_codec import decompress


def sha(data):
    return hashlib.sha256(data).hexdigest()


def add(entries, name, data, mode):
    require(name not in entries, 'Health overlay would overwrite ' + name)
    for index in range(1, len(Path(name).parts)):
        parent = '/'.join(Path(name).parts[:index])
        if parent not in entries:
            entries[parent] = {'mode': stat.S_IFDIR | 0o755, 'uid': 0, 'gid': 0,
                               'rdevmajor': 0, 'rdevminor': 0, 'data': b''}
        require(stat.S_ISDIR(entries[parent]['mode']), 'Non-directory parent ' + parent)
    entries[name] = {'mode': mode, 'uid': 0, 'gid': 0,
                     'rdevmajor': 0, 'rdevminor': 0, 'data': data}


def main():
    os.umask(0o077)
    require(not OUT.exists(), 'Refuse to overwrite existing health rootfs export')
    base = (SOURCE / 'alpine-openrc-rootfs.cpio.gz').read_bytes()
    manifest = json.loads((SOURCE / 'manifest.json').read_text())
    require(manifest.get('state') == 'verified-openrc-rootfs-payload' and
            sha(base) == manifest.get('archive_sha256'), 'Base OpenRC rootfs differs')
    entries = read_newc(gzip.decompress(base))
    supervisor = (PORT / 'lynx-health-supervisor.sh').read_bytes()
    service = (PORT / 'openrc-lynx-health').read_bytes()
    add(entries, 'usr/libexec/lynx-health-supervisor.sh', supervisor, stat.S_IFREG | 0o755)
    add(entries, 'etc/init.d/lynx-health', service, stat.S_IFREG | 0o755)
    add(entries, 'etc/runlevels/default/lynx-health', b'../../init.d/lynx-health', stat.S_IFLNK | 0o777)
    ordered = dict(sorted(entries.items(), key=lambda pair: (
        not stat.S_ISDIR(pair[1]['mode']), pair[0].count('/'), pair[0])))
    archive = gzip.compress(decompress(pack(ordered)), compresslevel=9, mtime=0)
    unpacked = read_newc(gzip.decompress(archive))
    require(len(unpacked) == len(entries) and all(
        name in unpacked and unpacked[name]['mode'] == item['mode'] and
        unpacked[name]['data'] == item['data'] for name, item in entries.items()),
        'Health rootfs round trip differs')
    OUT.mkdir(mode=0o700)
    target = OUT / 'alpine-openrc-health-rootfs.cpio.gz'
    target.write_bytes(archive)
    target.chmod(0o600)
    result = {
        'state': 'verified-openrc-health-rootfs-payload', 'created_ns': time.time_ns(),
        'archive': str(target), 'archive_sha256': sha(archive),
        'archive_bytes': len(archive), 'entries': len(entries),
        'base_openrc_sha256': sha(base), 'supervisor_sha256': sha(supervisor),
        'service_sha256': sha(service), 'roundtrip_verified': True,
        'phone_contacted': False, 'flash_performed': False,
        'limits': 'Offline Alpine/OpenRC RAM rootfs only. The phone still needs automatic matching module and watcher startup before it can use this service on an independent boot.'
    }
    (OUT / 'manifest.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'state': result['state'], 'archive_sha256': result['archive_sha256'],
                      'result': str(OUT / 'manifest.json')}))


if __name__ == '__main__':
    main()
