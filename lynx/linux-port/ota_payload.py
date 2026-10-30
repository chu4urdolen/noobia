"""Strict subset of AOSP update_metadata.proto for full OTA image extraction.

Schema: android.googlesource.com/platform/system/update_engine/+/refs/heads/main/update_metadata.proto
Only replacement/zero operations are supported; never applies a payload to a device.
"""
import bz2
import hashlib
import lzma
import struct


def varint(data, offset):
    value = 0
    for shift in range(0, 70, 7):
        if offset >= len(data):
            raise ValueError('Truncated protobuf varint')
        byte = data[offset]
        offset += 1
        if shift == 63 and byte > 1:
            raise ValueError('Protobuf varint overflow')
        value |= (byte & 127) << shift
        if byte < 128:
            return value, offset
    raise ValueError('Protobuf varint overflow')


def message(data):
    result = {}
    offset = 0
    while offset < len(data):
        tag, offset = varint(data, offset)
        field, wire = tag >> 3, tag & 7
        if not field:
            raise ValueError('Invalid protobuf field')
        if wire == 0:
            value, offset = varint(data, offset)
        elif wire in (1, 5):
            size = 8 if wire == 1 else 4
            if offset + size > len(data):
                raise ValueError('Truncated fixed protobuf field')
            value = data[offset:offset + size]
            offset += size
        elif wire == 2:
            size, offset = varint(data, offset)
            if offset + size > len(data):
                raise ValueError('Truncated protobuf bytes')
            value = data[offset:offset + size]
            offset += size
        else:
            raise ValueError('Unsupported protobuf wire type')
        result.setdefault(field, []).append((wire, value))
    return result


def one(fields, number, wire, default=None):
    values = fields.get(number, [])
    if not values:
        return default
    if len(values) != 1 or values[0][0] != wire:
        raise ValueError(f'Invalid singular field {number}')
    return values[0][1]


def repeated_messages(fields, number):
    for wire, value in fields.get(number, []):
        if wire != 2:
            raise ValueError('Expected protobuf message')
        yield message(value)


def parse_header(data):
    if len(data) != 24 or data[:4] != b'CrAU':
        raise ValueError('Invalid OTA payload header')
    version, manifest_size, signature_size = struct.unpack('>QQI', data[4:])
    if version != 2 or manifest_size > 8 * 1024 * 1024 or signature_size > 65536:
        raise ValueError('Unexpected OTA payload header values')
    return manifest_size, signature_size


def parse_manifest(data):
    fields = message(data)
    block_size = one(fields, 3, 0, 4096)
    minor = one(fields, 12, 0, 0)
    if block_size != 4096 or minor > 9:
        raise ValueError('Unsupported payload block size or minor version')
    partitions = {}
    for partition in repeated_messages(fields, 13):
        name = one(partition, 1, 2).decode()
        if name in partitions:
            raise ValueError('Duplicate partition name')
        info = message(one(partition, 7, 2))
        partitions[name] = {'size': one(info, 1, 0), 'hash': one(info, 2, 2),
                            'operations': list(repeated_messages(partition, 8)),
                            'manifest_minor_version': minor,
                            'old_partition_info_present': 6 in partition}
    return block_size, partitions


def reconstruct(partition, block_size, fetch_blob, max_size=67108864):
    size = partition['size']
    if not isinstance(size, int) or not 0 < size <= max_size or len(partition['hash']) != 32:
        raise ValueError('Unexpected selected partition size or digest')
    if partition['old_partition_info_present']:
        raise ValueError('Source-dependent partition cannot be extracted independently')
    image = bytearray(size)
    coverage = []
    for operation in partition['operations']:
        kind = one(operation, 1, 0)
        if kind not in (0, 1, 6, 8) or operation.get(4):
            raise ValueError(f'Source-dependent or unsupported operation {kind}')
        extents = []
        for extent in repeated_messages(operation, 6):
            start, length = one(extent, 1, 0), one(extent, 2, 0)
            if start is None or length is None or length <= 0:
                raise ValueError('Invalid destination extent')
            start, length = start * block_size, length * block_size
            if start + length > size:
                raise ValueError('Extent outside image')
            extents.append((start, length))
        wanted = sum(length for _, length in extents)
        if not wanted:
            raise ValueError('Empty operation')
        if kind == 6:
            if one(operation, 3, 0, 0):
                raise ValueError('ZERO unexpectedly has data')
            data = bytes(wanted)
        else:
            offset, length = one(operation, 2, 0, 0), one(operation, 3, 0)
            if length is None or not 0 < length <= 67108864:
                raise ValueError('Invalid operation blob length')
            blob = fetch_blob(offset, length)
            digest = one(operation, 8, 2)
            if digest is None or hashlib.sha256(blob).digest() != digest:
                raise ValueError('Operation data hash mismatch')
            if kind == 0:
                data = blob
            else:
                decoder = bz2.BZ2Decompressor() if kind == 1 else lzma.LZMADecompressor()
                data = decoder.decompress(blob, max_length=wanted + 1)
                if not decoder.eof or decoder.unused_data:
                    raise ValueError('Truncated, oversized or trailing compressed operation')
            if len(data) > wanted or wanted - len(data) >= block_size:
                raise ValueError('Wrong decompressed operation length')
            data += bytes(wanted - len(data))
        consumed = 0
        for start, length in extents:
            image[start:start + length] = data[consumed:consumed + length]
            consumed += length
            coverage.append((start, start + length))
    expected_start = 0
    for start, end in sorted(coverage):
        if start != expected_start:
            raise ValueError('Image extents overlap or leave a hole')
        expected_start = end
    if expected_start != size or hashlib.sha256(image).digest() != partition['hash']:
        raise ValueError('Final partition size or hash mismatch')
    return bytes(image)
