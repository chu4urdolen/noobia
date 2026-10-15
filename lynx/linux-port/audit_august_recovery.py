"""Assess the August package's device trees, recovery files and key continuity."""
import ctypes
import ctypes.util
import gzip
import hashlib
import json
from pathlib import Path
import re
import stat
import struct

from image_formats import read_boot_v4, read_newc, require

BASE = Path(__file__).resolve().parent
STOCK = BASE / 'artifacts/stock-cph2493-August-eu-ota'


def decompress_ramdisk(data):
    if data.startswith(b'\x1f\x8b'):
        return gzip.decompress(data)
    require(data[:4] == bytes.fromhex('02214c18'), 'Expected legacy LZ4 ramdisk')
    library = ctypes.CDLL(ctypes.util.find_library('lz4'))
    decode = library.LZ4_decompress_safe
    decode.argtypes = [ctypes.c_char_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
    decode.restype = ctypes.c_int
    offset, parts, total = 4, [], 0
    while offset < len(data):
        require(offset + 4 <= len(data), 'Truncated LZ4 block size')
        size = struct.unpack_from('<I', data, offset)[0]
        offset += 4
        if size == 0:
            require(not any(data[offset:]), 'LZ4 trailing data')
            break
        require(offset + size <= len(data), 'Truncated LZ4 block')
        output = ctypes.create_string_buffer(8 * 1024 * 1024)
        count = decode(data[offset:offset + size], output, size, len(output))
        require(count > 0, 'LZ4 decompression failed')
        total += count
        require(total <= 128 * 1024 * 1024, 'Ramdisk expansion limit')
        parts.append(output.raw[:count])
        offset += size
    return b''.join(parts)


def inspect_fdt(data):
    require(len(data) >= 40, 'Truncated FDT header')
    magic, total, off_structure, off_strings, off_reserved, version, compatible_version, cpu, strings_size, structure_size = struct.unpack_from('>10I', data)
    require(magic == 0xd00dfeed and 40 <= total <= len(data), 'Invalid FDT bounds')
    require(off_structure + structure_size <= total and off_strings + strings_size <= total,
            'FDT section outside declared size')
    strings = data[off_strings:off_strings + strings_size]
    end = off_structure + structure_size
    offset, stack, properties = off_structure, [], {}
    while offset < end:
        require(offset + 4 <= end, 'Truncated FDT token')
        token = struct.unpack_from('>I', data, offset)[0]
        offset += 4
        if token == 1:
            last = data.find(b'\0', offset, end)
            require(last >= 0, 'Unterminated FDT node')
            stack.append(data[offset:last].decode())
            offset = (last + 4) & ~3
        elif token == 2:
            require(bool(stack), 'FDT node-stack underflow')
            stack.pop()
        elif token == 3:
            require(offset + 8 <= end, 'Truncated FDT property')
            length, name_offset = struct.unpack_from('>II', data, offset)
            offset += 8
            require(stack and name_offset < len(strings) and offset + length <= end, 'Invalid FDT property bounds')
            last = strings.find(b'\0', name_offset)
            require(last >= 0, 'Unterminated FDT property name')
            name = strings[name_offset:last].decode()
            if len(stack) == 1 and name in ('compatible', 'model'):
                properties[name] = data[offset:offset + length].rstrip(b'\0').decode().split('\0')
            offset = (offset + length + 3) & ~3
        elif token == 4:
            pass
        elif token == 9:
            require(not stack and not any(data[offset:end]), 'Unexpected FDT trailer')
            return {'bytes': total, 'version': version, 'root_properties': properties,
                    'sha256': hashlib.sha256(data[:total]).hexdigest()}
        else:
            raise ValueError('Invalid FDT structure token')
    raise ValueError('Missing FDT end token')


dtb = (STOCK / 'unpacked-vendor-boot/dtb').read_bytes()
dtb_offset = dtb.find(bytes.fromhex('d00dfeed'))
require(dtb_offset in (0, 64), 'Unexpected vendor DTB wrapper')
dtb_report = inspect_fdt(dtb[dtb_offset:])
dtb_report['wrapper_bytes'] = dtb_offset
require(any(value.lower() == 'mediatek,mt6983' for value in dtb_report['root_properties'].get('compatible', [])),
        'DTB platform mismatch: ' + str(dtb_report['root_properties']))
dtbo = (STOCK / 'dtbo.img').read_bytes()
magic, total, header_size, entry_size, count, entry_offset, page, version = struct.unpack_from('>8I', dtbo)
require(magic == 0xd7b7ab1e and total <= len(dtbo) and header_size >= 32 and entry_size >= 32,
        'Invalid DTBO header')
require(0 < count <= 64 and entry_offset + count * entry_size <= total, 'Invalid DTBO table bounds')
overlays = []
for index in range(count):
    length, offset, identifier, revision, *custom = struct.unpack_from('>8I', dtbo, entry_offset + index * entry_size)
    require(offset + length <= total, 'DTBO payload outside table bounds')
    overlays.append({'id': identifier, 'revision': revision, 'custom': custom,
                     'fdt': inspect_fdt(dtbo[offset:offset + length])})
boot = read_boot_v4((STOCK / 'boot.img').read_bytes())
generic = read_newc(decompress_ramdisk(boot['ramdisk']))
vendor = read_newc(decompress_ramdisk((STOCK / 'unpacked-vendor-boot/vendor_ramdisk00').read_bytes()))
recovery_entries = []
for name, entry in vendor.items():
    if name == 'init' or 'recovery' in name or name.endswith('/init'):
        item = {'path': name, 'mode': oct(entry['mode']), 'bytes': len(entry['data']),
                'sha256': hashlib.sha256(entry['data']).hexdigest()}
        if stat.S_ISLNK(entry['mode']):
            item['symlink_target'] = entry['data'].decode()
        recovery_entries.append(item)
require('init' in generic and any(item['path'].endswith('/recovery') for item in recovery_entries),
        'Expected stock init and recovery executable missing')
august_avb = json.loads((BASE / 'docs/august-stock-avb-audit.json').read_text())
july_avb = json.loads((BASE / 'docs/stock-avb-audit.json').read_text())
keys = {name: item.get('embedded_key_sha256') == july_avb['images'][name].get('embedded_key_sha256')
        for name, item in august_avb['images'].items() if item.get('embedded_key_sha256')}
report = {'reference_package': 'CPH2493_13.1.0.561(EX01)', 'dtb': dtb_report,
          'dtbo_entries': overlays, 'generic_ramdisk_entries': len(generic),
          'vendor_ramdisk_entries': len(vendor), 'stock_generic_init_sha256': hashlib.sha256(generic['init']['data']).hexdigest(),
          'vendor_recovery_entries': recovery_entries,
          'avb_keys_match_july_reference': keys,
          'package_supports_preparing_stock_boot_chain_restoration': True,
          'recovery_boot_on_lynx_verified': False,
          'installed_vendor_boot_and_dtbo_read_back': False,
          'phone_stored_rollback_indexes_known': False,
          'bootloader_write_support_tested': False,
          'phone_contacted': False, 'flash_eligible': False,
          'conclusion': 'Correct-model boot-chain reference with a matching LK build; actual restoration and recovery boot remain untested.'}
(BASE / 'docs/august-recovery-audit.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({name: value for name, value in report.items() if name not in ('dtbo_entries', 'vendor_recovery_entries')}, indent=2))
