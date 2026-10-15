"""Locate embedded XZ kernel headers in the saved stock boot image, offline.

Only saves the validated compressed archive and an inventory. Does not extract
paths, execute archive content, build/load modules, or contact the handset.
"""
import gzip
import hashlib
import io
import json
import lzma
import sys
import tarfile
import time
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent.parent
PORT = ROOT / 'linux-port'
sys.path.insert(0, str(PORT))
from image_formats import read_boot_v4

STOCK_SHA = 'a67f03d7b826b834c23653b67eaa6efa971eb70ef8af19eee4d33fb5fc7fe995'
LIMIT = 128 * 1024 * 1024


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    boot = (PORT / 'artifacts/stock-cph2493-August-eu-ota/boot.img').read_bytes()
    if sha(boot) != STOCK_SHA:
        raise ValueError('Stock boot image hash differs')
    image = gzip.decompress(read_boot_v4(boot)['kernel'])
    out = PORT / 'artifacts' / ('stock-embedded-headers-' + str(time.time_ns()))
    out.mkdir(mode=0o700)
    rows = []
    found = []
    offset = 0
    while True:
        offset = image.find(b'\xfd7zXZ\x00', offset)
        if offset < 0:
            break
        row = {'image_offset': offset}
        try:
            decoder = lzma.LZMADecompressor(format=lzma.FORMAT_XZ, memlimit=LIMIT)
            data = decoder.decompress(image[offset:], max_length=LIMIT)
            if not decoder.eof:
                raise ValueError('XZ exceeds output bound or is incomplete')
            consumed = len(image) - offset - len(decoder.unused_data)
            with tarfile.open(fileobj=io.BytesIO(data), mode='r:') as archive:
                members = archive.getmembers()
                names = set()
                inventory = []
                for member in members:
                    path = PurePosixPath(member.name)
                    if path.is_absolute() or '..' in path.parts or not (member.isfile() or member.isdir() or member.issym()):
                        raise ValueError('Unsafe archive member')
                    name = str(path)
                    if name in names:
                        raise ValueError('Duplicate archive member')
                    names.add(name)
                    if member.isfile():
                        content = archive.extractfile(member).read()
                        inventory.append({'path': name, 'bytes': len(content), 'sha256': sha(content)})
                    elif member.issym():
                        # Retain metadata only: some OEM links name files outside
                        # the header subset. Never follow or extract these links.
                        inventory.append({'path': name, 'type': 'symlink-not-followed',
                                          'target': member.linkname})
                required = {'include/linux/i2c.h', 'include/linux/module.h',
                            'include/generated/autoconf.h', 'include/generated/utsrelease.h'}
                if not required <= names:
                    raise ValueError('Not the required kernel-header archive')
                release = archive.extractfile(next(m for m in members if str(PurePosixPath(m.name)) == 'include/generated/utsrelease.h')).read().decode()
                expected = '5.10.149-android12-9-o-g311738fbb5a8'
                if expected not in release:
                    raise ValueError('Embedded release does not match the working kernel')
            target = out / ('kheaders-' + str(offset) + '.tar.xz')
            target.write_bytes(image[offset:offset + consumed])
            row.update(state='headers-verified', archive=target.name, archive_bytes=consumed,
                       archive_sha256=sha(target.read_bytes()), uncompressed_bytes=len(data),
                       header_files=sum('sha256' in item for item in inventory),
                       symlinks_not_followed=sum(item.get('type') == 'symlink-not-followed' for item in inventory),
                       kernel_release=expected)
            (out / ('inventory-' + str(offset) + '.json')).write_text(json.dumps(inventory, indent=2) + '\n')
            found.append(row)
        except (ValueError, lzma.LZMAError, tarfile.TarError) as error:
            row.update(state='not-usable-headers', reason=str(error))
        rows.append(row)
        offset += 6
    result = {'stock_boot_sha256': STOCK_SHA, 'kernel_image_sha256': sha(image),
              'phone_contacted': False, 'modules_built_or_loaded': False,
              'candidates': rows, 'verified_header_archives': len(found),
              'limits': 'Headers alone do not provide Module.symvers, a build system, or matching CFI compiler. No module ABI compatibility or battery sensing is claimed.'}
    (out / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'result': str(out / 'result.json'), 'verified': found}, indent=2))
    if len(found) != 1:
        raise SystemExit('Expected exactly one verified embedded-header archive')


if __name__ == '__main__':
    main()
