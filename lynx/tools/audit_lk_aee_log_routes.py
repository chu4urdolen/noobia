"""Offline AArch64 stock AEE crash-handler string references; no phone access."""
import hashlib
import json
from pathlib import Path
import re
import struct

from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM

BASE = Path(__file__).resolve().parent.parent / 'linux-port'
IMAGE = BASE / 'artifacts/stock-cph2493-August-eu-ota/lk.img'
EXPECTED = '78db9e36426faa5f20487a39f136eecea785a9122cfe1fc25056a758953d7231'


def signed(value, bits):
    return value - (1 << bits) if value & (1 << (bits - 1)) else value


def main():
    data = IMAGE.read_bytes()
    if hashlib.sha256(data).hexdigest() != EXPECTED:
        raise ValueError('Reference LK changed')
    section_offset = 0x1b73d0
    if struct.unpack_from('<I', data, section_offset)[0] != 0x58881688 or data[section_offset+8:section_offset+12] != b'aee\x00':
        raise ValueError('Stock AEE section changed')
    size = struct.unpack_from('<I', data, section_offset+4)[0]
    payload = data[section_offset+512:section_offset+512+size]
    if len(payload) != size: raise ValueError('Truncated AEE payload')
    base = 0x100000
    strings = []
    wanted = re.compile(r'^oem |mrdump_read_expdb|Compress expdb|read expdb fail|SYS_PSTORE_RAW|SYS_RAMCONSOLE_RAW|pstore_raw|log_store_buf_map')
    for match in re.finditer(rb'[\x20-\x7e]{5,}', payload):
        text = match.group().decode()
        if wanted.search(text):
            strings.append({'file_offset': match.start() + section_offset + 512, 'relative_offset': match.start(),
                            'analysis_address': base + match.start(), 'text': text})
    by_address = {item['analysis_address']: item for item in strings}
    # Compilers may merge "dump_pllk_log" with the suffix of
    # "oem dump_pllk_log"; OEM dispatch then references the inner string.
    for item in strings:
        if item['text'].startswith('oem '):
            by_address[item['analysis_address'] + 4] = dict(item, text=item['text'] + ' [suffix reference]')
    references = []
    words = list(struct.unpack('<' + 'I' * (len(payload) // 4), payload[:len(payload) // 4 * 4]))
    for i, word in enumerate(words):
        kind = word & 0x9f000000
        if kind not in (0x10000000, 0x90000000):
            continue
        immediate = signed((((word >> 5) & 0x7ffff) << 2) | ((word >> 29) & 3), 21)
        register = word & 31
        pc = base + i * 4
        address = pc + immediate if kind == 0x10000000 else (pc & ~4095) + (immediate << 12)
        targets = [(i, address)] if kind == 0x10000000 else []
        if kind == 0x90000000:
            for j in range(i + 1, min(i + 257, len(words))):
                following = words[j]
                if following & 0xff800000 == 0x91000000 and (following >> 5) & 31 == register:
                    offset = ((following >> 10) & 0xfff) << (12 if following & (1 << 22) else 0)
                    targets.append((j, address + offset))
        for j, target in targets:
            if target not in by_address:
                continue
            start = max(0, j * 4 - 48)
            end = min(len(payload), j * 4 + 80)
            md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
            instructions = [{'address': hex(ins.address), 'mnemonic': ins.mnemonic, 'operands': ins.op_str}
                            for ins in md.disasm(payload[start:end], base + start)]
            references.append({'string': by_address[target]['text'], 'reference_address': hex(pc),
                               'destination_register': register, 'instructions': instructions})
    report = {'image_sha256': EXPECTED, 'section_offset': hex(section_offset), 'section_name': 'aee', 'payload_bytes': len(payload), 'analysis_base': hex(base),
              'strings': strings, 'references': references, 'phone_contacted': False,
              'command_handler_semantics_proven': False,
              'limits': ['Addresses use an offline analysis base, not a runtime physical or virtual address.',
                         'Linear instruction-pattern matching may include data false positives.',
                         'Only the AEE MTK-header payload is inspected; no complete control-flow proof or runtime mode accessibility established.']}
    output = BASE / 'docs/lk-aee-log-route-audit.json'
    output.write_text(json.dumps(report, indent=2) + '\n')
    for item in references:
        if item['string'] in ('oem mrdump', 'oem mrdump [suffix reference]'):
            print(item['string'], 'reference', item['reference_address'])
            for ins in item['instructions']:
                print(ins['address'], ins['mnemonic'], ins['operands'])
    print('Preserved references:', len(references), 'at', output)


if __name__ == '__main__':
    main()
