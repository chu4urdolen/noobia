"""Inspect ramdisk overlap without executing stock code or touching the phone."""
import ctypes
import ctypes.util
import gzip
import hashlib
import json
from pathlib import Path
import stat
import struct

from image_formats import read_boot_v4, read_newc, require

base = Path(__file__).resolve().parent
stock = base / 'artifacts/stock-cph2493-A10'


def decompress(data):
    if data[:2] == b'\x1f\x8b':
        return gzip.decompress(data)
    require(data[:4] == bytes.fromhex('02214c18'), 'Unsupported ramdisk compression')
    library = ctypes.CDLL(ctypes.util.find_library('lz4'))
    decode = library.LZ4_decompress_safe
    decode.argtypes = [ctypes.c_char_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
    decode.restype = ctypes.c_int
    offset, parts = 4, []
    while offset < len(data):
        require(offset + 4 <= len(data), 'Truncated LZ4 block header')
        size = struct.unpack_from('<I', data, offset)[0]
        offset += 4
        if size == 0:
            require(not any(data[offset:]), 'Unexpected LZ4 trailing bytes')
            break
        require(offset + size <= len(data), 'Truncated LZ4 block')
        buffer = ctypes.create_string_buffer(8 * 1024 * 1024)
        count = decode(data[offset:offset + size], buffer, size, len(buffer))
        require(count > 0, 'Invalid LZ4 block')
        parts.append(buffer.raw[:count])
        offset += size
    return b''.join(parts)


def describe(name, entry):
    result = {'path': name, 'mode': oct(entry['mode']), 'bytes': len(entry['data']),
              'sha256': hashlib.sha256(entry['data']).hexdigest()}
    if stat.S_ISLNK(entry['mode']):
        result['symlink_target'] = entry['data'].decode()
    return result


generic = read_newc(decompress(read_boot_v4((stock / 'boot.img').read_bytes())['ramdisk']))
vendor = read_newc(decompress((stock / 'vendor-ramdisk.bin').read_bytes()))
candidate = read_newc(gzip.decompress((base / 'artifacts/busybox-offline/initramfs.cpio.gz').read_bytes()))
important = lambda name: name == 'init' or 'recovery' in name or name.endswith('/init')
report = {
    'device': 'Lynx / OnePlus Nord 3 CPH2493',
    'reference_package_only': True,
    'generic_entries': len(generic), 'vendor_entries': len(vendor),
    'stock_generic_recovery_entries': [describe(n, e) for n, e in generic.items() if important(n)],
    'stock_vendor_recovery_entries': [describe(n, e) for n, e in vendor.items() if important(n)],
    'candidate_changes_vendor_files': [n for n in sorted(candidate.keys() & vendor.keys())
                                      if not stat.S_ISDIR(candidate[n]['mode'])
                                      and (candidate[n]['data'] != vendor[n]['data']
                                           or candidate[n]['mode'] != vendor[n]['mode'])],
    'identical_overlaid_vendor_modules': [n for n in sorted(candidate.keys() & vendor.keys())
                                        if n.endswith('.ko') and candidate[n]['data'] == vendor[n]['data']],
    'stock_generic_init': describe('init', generic['init']) if 'init' in generic else None,
    'candidate_init': describe('init', candidate['init']),
    'recovery_preservation_proven': False,
    'flash_eligible': False,
    'conclusion': 'Replacing the generic init changes early startup; unchanged vendor_boot alone does not prove recovery preservation.',
    'next_requirements': [
        'Match installed firmware and obtain original partition backups through an established read-only route.',
        'Determine the actual recovery boot signal and stock init handoff before designing a dispatcher.',
        'Validate physical recovery and restoration with matching images before any stored-image Linux test.'
    ],
    'source': 'https://source.android.com/docs/core/architecture/partitions/vendor-boot-partitions'
}
(base / 'docs/recovery-boundary-audit.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
