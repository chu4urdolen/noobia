"""Bounded gzip/legacy-LZ4 ramdisk codecs using the existing local LZ4 library."""
import ctypes
import ctypes.util
import gzip
import struct

from image_formats import require

MAGIC = bytes.fromhex('02214c18')
BLOCK = 8 * 1024 * 1024


def library():
    return ctypes.CDLL(ctypes.util.find_library('lz4'))


def decompress(data):
    if data.startswith(b'\x1f\x8b'):
        return gzip.decompress(data)
    require(data.startswith(MAGIC), 'Unsupported ramdisk codec')
    lib = library()
    decode = lib.LZ4_decompress_safe
    decode.argtypes = [ctypes.c_char_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
    decode.restype = ctypes.c_int
    offset, total, parts = 4, 0, []
    while offset < len(data):
        require(offset + 4 <= len(data), 'Truncated LZ4 block size')
        count = struct.unpack_from('<I', data, offset)[0]
        offset += 4
        if count == 0:
            require(not any(data[offset:]), 'Unexpected LZ4 trailer')
            break
        require(count <= BLOCK + BLOCK // 255 + 16 and offset + count <= len(data), 'Invalid LZ4 compressed block bounds')
        output = ctypes.create_string_buffer(BLOCK)
        size = decode(data[offset:offset + count], output, count, BLOCK)
        require(size > 0, 'Invalid LZ4 compressed data')
        total += size
        require(total <= 128 * 1024 * 1024, 'Ramdisk expansion limit exceeded')
        parts.append(output.raw[:size])
        offset += count
    return b''.join(parts)


def compress_legacy(data):
    require(len(data) <= 128 * 1024 * 1024, 'Ramdisk input too large')
    lib = library()
    bound = lib.LZ4_compressBound
    bound.argtypes = [ctypes.c_int]
    bound.restype = ctypes.c_int
    encode = lib.LZ4_compress_HC
    encode.argtypes = [ctypes.c_char_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int]
    encode.restype = ctypes.c_int
    output = bytearray(MAGIC)
    for offset in range(0, len(data), BLOCK):
        chunk = data[offset:offset + BLOCK]
        destination = ctypes.create_string_buffer(bound(len(chunk)))
        length = encode(chunk, destination, len(chunk), len(destination), 12)
        require(length > 0, 'LZ4 compression failed')
        output += struct.pack('<I', length) + destination.raw[:length]
    require(decompress(bytes(output)) == data, 'LZ4 roundtrip changed ramdisk')
    return bytes(output)
