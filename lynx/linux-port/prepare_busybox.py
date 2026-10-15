"""Obtain Alpine's static ARM64 BusyBox; validate index and data checksums."""
import base64
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import struct
import tarfile
import urllib.request
import zlib

base = Path(__file__).resolve().parent
artifacts = base / 'artifacts'
with tarfile.open(artifacts / 'APKINDEX-aarch64.tar.gz', 'r:gz') as index:
    text = index.extractfile('APKINDEX').read().decode()
block = next(b for b in text.split('\n\n') if '\nP:busybox-static\n' in '\n' + b + '\n')
fields = dict(line.split(':', 1) for line in block.splitlines() if ':' in line)
assert fields['A'] == 'aarch64'
version = fields['V']
assert re.fullmatch(r'[0-9.]+-r[0-9]+', version)
url = 'https://dl-cdn.alpinelinux.org/alpine/latest-stable/main/aarch64/busybox-static-' + version + '.apk'
apk_path = artifacts / ('busybox-static-' + version + '.apk')
if not apk_path.exists():
    with urllib.request.urlopen(url, timeout=30) as response:
        apk_path.write_bytes(response.read())
raw = apk_path.read_bytes()
streams = []
remaining = raw
while remaining:
    decoder = zlib.decompressobj(31)
    unpacked = decoder.decompress(remaining)
    assert decoder.eof
    consumed = len(remaining) - len(decoder.unused_data)
    streams.append((remaining[:consumed], unpacked))
    remaining = decoder.unused_data
assert len(streams) == 3, 'Expected APK v2 signature/control/data streams'
assert fields['C'].startswith('Q1')
assert hashlib.sha1(streams[1][0]).digest() == base64.b64decode(fields['C'][2:]), 'APK control checksum differs from repository index'
with tarfile.open(fileobj=io.BytesIO(streams[1][1]), mode='r:') as control:
    pkginfo = control.extractfile('.PKGINFO').read().decode()
data_hash = next(line.split(' = ', 1)[1] for line in pkginfo.splitlines() if line.startswith('datahash = '))
assert hashlib.sha256(streams[2][0]).hexdigest() == data_hash, 'APK payload checksum mismatch'
with tarfile.open(fileobj=io.BytesIO(streams[2][1]), mode='r:') as payload:
    busybox = payload.extractfile('bin/busybox.static').read()
assert busybox[:6] == b'\x7fELF\x02\x01', 'Expected 64-bit little-endian ELF'
assert struct.unpack_from('<H', busybox, 18)[0] == 183, 'Expected AArch64'
ph_offset = struct.unpack_from('<Q', busybox, 32)[0]
ph_size, ph_count = struct.unpack_from('<HH', busybox, 54)
ph_types = [struct.unpack_from('<I', busybox, ph_offset + i * ph_size)[0] for i in range(ph_count)]
assert 3 not in ph_types, 'Static executable must not require an ELF interpreter'
# Static PIE may have a dynamic segment for self-relocations, but no DT_NEEDED libraries.
for i in range(ph_count):
    pos = ph_offset + i * ph_size
    if struct.unpack_from('<I', busybox, pos)[0] == 2:
        dynamic_offset = struct.unpack_from('<Q', busybox, pos + 8)[0]
        dynamic_size = struct.unpack_from('<Q', busybox, pos + 32)[0]
        tags = [struct.unpack_from('<Q', busybox, j)[0] for j in range(dynamic_offset, dynamic_offset + dynamic_size, 16)]
        assert 1 not in tags, 'Static executable must not require shared libraries'
binary = artifacts / 'busybox-aarch64-static'
binary.write_bytes(busybox)
binary.chmod(0o755)
report = {'url': url, 'version': version, 'arch': 'aarch64', 'index_control_checksum_verified': True, 'package_data_checksum_verified': True, 'publisher_signature_verified': False, 'package_sha256': hashlib.sha256(raw).hexdigest(), 'binary_sha256': hashlib.sha256(busybox).hexdigest(), 'binary_size': len(busybox), 'static_elf_verified': True}
(base / 'docs/busybox-provenance.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
