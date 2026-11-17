"""Strict readers for the offline native bring-up artifacts."""
from pathlib import PurePosixPath
import struct


def require(condition, message):
    if not condition:
        raise ValueError(message)


def elf64(data):
    require(len(data) >= 64 and data[:6] == b'\x7fELF\x02\x01', 'Expected ELF64 little-endian')
    machine = struct.unpack_from('<H', data, 18)[0]
    phoff, shoff = struct.unpack_from('<QQ', data, 32)
    phsize, phcount, shsize, shcount, shstrings = struct.unpack_from('<5H', data, 54)
    require(not phcount or phsize >= 56, 'Invalid ELF program header size')
    require(phoff + phsize * phcount <= len(data), 'Truncated ELF program headers')
    require(not shcount or shsize >= 64, 'Invalid ELF section header size')
    require(shoff + shsize * shcount <= len(data), 'Truncated ELF section headers')
    programs = [struct.unpack_from('<IIQQQQQQ', data, phoff + i * phsize) for i in range(phcount)]
    for header in programs:
        require(header[2] + header[5] <= len(data), 'Truncated ELF program segment')
    sections = [struct.unpack_from('<IIQQQQIIQQ', data, shoff + i * shsize) for i in range(shcount)]
    named = {}
    if sections:
        require(shstrings < shcount, 'Invalid ELF section-name index')
        table = sections[shstrings]
        names = data[table[4]:table[4] + table[5]]
        for section in sections:
            require(section[0] < len(names), 'Invalid ELF section name')
            end = names.find(b'\0', section[0])
            require(end >= 0, 'Unterminated ELF section name')
            name = names[section[0]:end].decode()
            if section[1] != 8:  # SHT_NOBITS has no file payload.
                require(section[4] + section[5] <= len(data), 'Truncated ELF section')
                named[name] = data[section[4]:section[4] + section[5]]
    return {'machine': machine, 'programs': programs, 'sections': named}


def static_aarch64(data):
    parsed = elf64(data)
    require(parsed['machine'] == 183, 'Executable is not AArch64')
    for header in parsed['programs']:
        require(header[0] != 3, 'Executable requires a dynamic interpreter')
        if header[0] == 2:
            require(header[5] % 16 == 0, 'Malformed ELF dynamic segment')
            tags = [struct.unpack_from('<Q', data, i)[0] for i in range(header[2], header[2] + header[5], 16)]
            require(1 not in tags, 'Executable requires shared libraries')
    return parsed


def module_metadata(data):
    parsed = elf64(data)
    require(parsed['machine'] == 183, 'Kernel module is not AArch64')
    require('.modinfo' in parsed['sections'], 'Kernel module lacks .modinfo')
    values = {}
    for item in parsed['sections']['.modinfo'].split(b'\0'):
        if b'=' in item:
            key, value = item.split(b'=', 1)
            values.setdefault(key.decode(), []).append(value.decode(errors='replace'))
    require('vermagic' in values, 'Kernel module lacks vermagic')
    return {'values': values, 'has_symbol_versions': bool(parsed['sections'].get('__versions'))}


def read_newc(data):
    entries = {}
    offset = 0
    while offset + 110 <= len(data):
        require(data[offset:offset + 6] == b'070701', 'Expected newc archive header')
        try:
            fields = [int(data[offset + 6 + i * 8:offset + 14 + i * 8], 16) for i in range(13)]
        except ValueError as error:
            raise ValueError('Malformed newc fields') from error
        mode, size, namesize = fields[1], fields[6], fields[11]
        require(namesize > 0 and offset + 110 + namesize <= len(data), 'Truncated newc name')
        start = offset + 110
        require(data[start + namesize - 1] == 0, 'Unterminated newc name')
        name = data[start:start + namesize - 1].decode()
        path = PurePosixPath(name)
        require(not path.is_absolute() and '..' not in path.parts, 'Unsafe newc path')
        payload_offset = (start + namesize + 3) & ~3
        require(payload_offset + size <= len(data), 'Truncated newc payload')
        payload = data[payload_offset:payload_offset + size]
        offset = (payload_offset + size + 3) & ~3
        if name == 'TRAILER!!!':
            require(size == 0 and not any(data[offset:]), 'Unexpected bytes after newc trailer')
            return entries
        require(name not in entries, 'Duplicate newc path')
        entries[name] = {'mode': mode, 'uid': fields[2], 'gid': fields[3], 'rdevmajor': fields[9], 'rdevminor': fields[10], 'data': payload}
    raise ValueError('Missing newc trailer')


def read_boot_v4(data):
    require(len(data) >= 4096 and data[:8] == b'ANDROID!', 'Invalid Android boot image')
    require(struct.unpack_from('<I', data, 40)[0] == 4, 'Expected boot header version 4')
    kernel_size, ramdisk_size, _, header_size = struct.unpack_from('<4I', data, 8)
    require(header_size == 1584, 'Unexpected boot v4 header size')
    align = lambda value: (value + 4095) // 4096 * 4096
    ramdisk_offset = 4096 + align(kernel_size)
    signature_size = struct.unpack_from('<I', data, 1580)[0]
    minimum_size = ramdisk_offset + align(ramdisk_size) + signature_size
    require(minimum_size <= len(data), 'Truncated boot image payload')
    return {'kernel': data[4096:4096 + kernel_size], 'ramdisk': data[ramdisk_offset:ramdisk_offset + ramdisk_size], 'signature_size': signature_size, 'cmdline': data[44:1580].split(b'\0', 1)[0].decode()}
