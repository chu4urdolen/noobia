"""Strict in-memory reader for the signature-verified ARM64 mini-rootfs."""
import hashlib
import json
import stat
import sys
import tarfile
from pathlib import Path, PurePosixPath

from fetch_alpine_rootfs import FINGERPRINT, VERSION

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'linux-port'))
from image_formats import elf64

ARCHIVE_SHA256 = '9bf70a7f18ea44094cbb5f70c58f9af129c8214745743db0e68e5502cc2ce773'
PROBE = '''set -eu
printf 'LYNX_ALPINE_USERSPACE_BEGIN\\n'
test "$(uname -m)" = aarch64
test "$(cat /etc/alpine-release)" = 3.24.2
uname -r
id
/sbin/apk --version
/sbin/apk info -e musl busybox alpine-baselayout alpine-keys
printf 'LYNX_ALPINE_USERSPACE_PASS\\n'
'''


def read_rootfs(receipt):
    report = json.loads(receipt.read_text())
    if not (report.get('passed') and report.get('signature_verified') and report.get('version') == VERSION
            and report.get('primary_fingerprint') == FINGERPRINT):
        raise ValueError('Matching release-signature receipt required')
    archive = Path(report['archive'])
    raw = archive.read_bytes()
    if hashlib.sha256(raw).hexdigest() != ARCHIVE_SHA256 or report['sha256'] != ARCHIVE_SHA256:
        raise ValueError('Pinned rootfs archive changed')
    entries, total = {}, 0
    with tarfile.open(archive, 'r:gz') as source:
        for member in source:
            path = PurePosixPath(member.name)
            if path.is_absolute() or '..' in path.parts:
                raise ValueError('Unsafe archive member')
            name = str(path)
            if name == '.':
                continue
            if name in entries or len(entries) >= 4096:
                raise ValueError('Duplicate/excessive archive members')
            if member.isdir():
                mode, data = stat.S_IFDIR, b''
            elif member.issym():
                mode, data = stat.S_IFLNK, member.linkname.encode()
            elif member.isfile() and member.size <= 16 * 1024 * 1024:
                mode, data = stat.S_IFREG, source.extractfile(member).read()
                if len(data) != member.size:
                    raise ValueError('Truncated member')
                total += len(data)
            else:
                raise ValueError('Unsupported archive type or file size')
            if total > 64 * 1024 * 1024:
                raise ValueError('Rootfs expansion cap exceeded')
            entries[name] = {'mode': mode | member.mode, 'uid': member.uid, 'gid': member.gid,
                             'rdevmajor': 0, 'rdevminor': 0, 'data': data}
    for name in entries:
        for parent in PurePosixPath(name).parents:
            if str(parent) in entries and not stat.S_ISDIR(entries[str(parent)]['mode']):
                raise ValueError('Archive member below a non-directory parent')
    # No host filesystem extraction or traversal through archive symlinks.
    def resolve(name):
        for _ in range(40):
            parts = PurePosixPath(name).parts
            for index in range(len(parts)):
                prefix = '/'.join(parts[:index + 1])
                item = entries.get(prefix)
                if item and stat.S_ISLNK(item['mode']):
                    target = item['data'].decode()
                    components = ([] if target.startswith('/') else list(parts[:index])) + target.split('/') + list(parts[index + 1:])
                    normalized = []
                    for component in components:
                        if component in ('', '.'):
                            continue
                        if component == '..':
                            if not normalized:
                                raise ValueError('Link escapes rootfs')
                            normalized.pop()
                        else:
                            normalized.append(component)
                    name = '/'.join(normalized)
                    break
            else:
                return entries[name]
        raise ValueError('Symlink cycle')
    elfs = []
    for name, item in entries.items():
        if stat.S_ISREG(item['mode']) and item['data'].startswith(b'\x7fELF'):
            parsed = elf64(item['data'])
            if parsed['machine'] != 183:
                raise ValueError('Non-ARM64 executable: ' + name)
            for header in parsed['programs']:
                if header[0] == 3:
                    interpreter = item['data'][header[2]:header[2] + header[5]].rstrip(b'\0').decode()
                    resolve(interpreter.lstrip('/'))
            elfs.append(name)
    for name in ['bin/sh', 'bin/busybox', 'sbin/apk']:
        if not stat.S_ISREG(resolve(name)['mode']):
            raise ValueError('Missing executable: ' + name)
    if entries['etc/alpine-release']['data'].strip() != VERSION.encode():
        raise ValueError('Unexpected rootfs release')
    return entries, {'archive': str(archive), 'archive_sha256': ARCHIVE_SHA256,
                     'entries': len(entries), 'regular_file_bytes': total, 'arm64_elf_files': elfs,
                     'archive_parent_paths_checked': True, 'host_extraction_performed': False}
