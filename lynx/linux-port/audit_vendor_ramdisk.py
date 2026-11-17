"""Inspect stock LZ4/newc ramdisk modules without running their contents."""
import ctypes
import ctypes.util
import gzip
import json
from pathlib import Path, PurePosixPath
import re
import stat
import struct
import hashlib
import argparse
from image_formats import module_metadata

base = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument('--stock-dir', type=Path, default=base / 'artifacts/stock-cph2493-A10')
parser.add_argument('--ramdisk', type=Path)
parser.add_argument('--kernel', type=Path)
parser.add_argument('--report', type=Path, default=base / 'docs/vendor-ramdisk-audit.json')
args = parser.parse_args()
stock = args.stock_dir.resolve()
if not stock.is_relative_to(base / 'artifacts') or not args.report.resolve().is_relative_to(base):
    raise ValueError('Keep extracted files and reports inside the Lynx workspace')
output = stock / 'vendor-ramdisk-unpacked'
output.mkdir(exist_ok=True)
ramdisk_path = args.ramdisk or stock / 'vendor-ramdisk.bin'
data = ramdisk_path.read_bytes()
if data[:4] == bytes.fromhex('02214c18'):
    library = ctypes.CDLL(ctypes.util.find_library('lz4'))
    decode = library.LZ4_decompress_safe
    decode.argtypes = [ctypes.c_char_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
    decode.restype = ctypes.c_int
    parts = []
    offset = 4
    while offset + 4 <= len(data):
        size = struct.unpack_from('<I', data, offset)[0]
        offset += 4
        if size == 0:
            break
        assert offset + size <= len(data), 'Truncated LZ4 block'
        buffer = ctypes.create_string_buffer(8 * 1024 * 1024)
        count = decode(data[offset:offset + size], buffer, size, len(buffer))
        assert count > 0, 'Invalid LZ4 block'
        parts.append(buffer.raw[:count])
        offset += size
    data = b''.join(parts)
elif data[:2] == b'\x1f\x8b':
    data = gzip.decompress(data)
else:
    raise RuntimeError('Unrecognized vendor ramdisk compression: ' + data[:8].hex())

entries = []
offset = 0
while offset + 110 <= len(data):
    assert data[offset:offset + 6] in (b'070701', b'070702'), f'Invalid newc header at {offset}'
    fields = [int(data[offset + 6 + i * 8:offset + 14 + i * 8], 16) for i in range(13)]
    mode, size, name_size = fields[1], fields[6], fields[11]
    start = offset + 110
    name = data[start:start + name_size - 1].decode()
    content_start = (start + name_size + 3) & ~3
    payload = data[content_start:content_start + size]
    offset = (content_start + size + 3) & ~3
    if name == 'TRAILER!!!':
        break
    path = PurePosixPath(name)
    assert not path.is_absolute() and '..' not in path.parts, name
    entry = {'path': name, 'size': size, 'mode': oct(mode), 'sha256': hashlib.sha256(payload).hexdigest()}
    if stat.S_ISREG(mode) and (name.endswith(('.ko', '.rc')) or 'modules.' in path.name or 'fstab' in path.name):
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
    if name.endswith('.ko'):
        metadata = module_metadata(payload)
        for key in ('vermagic', 'depends', 'name'):
            if key in metadata['values']:
                entry[key] = metadata['values'][key][0]
        entry['has_symbol_versions'] = metadata['has_symbol_versions']
    entries.append(entry)

image = (args.kernel or stock / 'Image').read_bytes()
if image.startswith(b'\x1f\x8b'):
    image = gzip.decompress(image)
banners = [x.decode(errors='replace') for x in re.findall(rb'Linux version [0-9][^\x00\n]{0,400}', image)]
report = {'uncompressed_size': len(data), 'entries': entries, 'kernel_banners': banners, 'stock_vendor_boot_sha256': hashlib.sha256((stock / 'vendor_boot.img').read_bytes()).hexdigest(), 'compressed_ramdisk_sha256': hashlib.sha256(ramdisk_path.read_bytes()).hexdigest()}
args.report.write_text(json.dumps(report, indent=2) + '\n')
print('Vendor ramdisk:', len(data), 'bytes;', len(entries), 'entries')
print('Kernel:', banners)
for entry in entries:
    if entry['path'].endswith('.ko') and any(term in entry['path'].lower() for term in ('mtu3', 'phy', 'pinctrl', 'clk-mt6983', 'scpsys', 'usb', 'watchdog')):
        print(json.dumps(entry))
