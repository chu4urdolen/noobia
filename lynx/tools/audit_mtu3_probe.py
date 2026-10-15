"""Inspect the pinned stock MTU3 probe entry and its imported call sites offline."""
import hashlib
import json
from pathlib import Path
import struct
from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM

ROOT = Path(__file__).resolve().parent.parent
PROJECT = ROOT / 'linux-port'
MODULE = PROJECT / 'artifacts/stock-cph2493-August-eu-ota/vendor-ramdisk-unpacked/lib/modules/mtu3.ko'


def main():
    data = MODULE.read_bytes()
    assert hashlib.sha256(data).hexdigest() == 'd3c59fa794a6e02f014dd0de660592bb66c9d7f8eb941c1d1183f8a3322bb467'
    shoff = struct.unpack_from('<Q', data, 40)[0]
    shsize, count, names_index = struct.unpack_from('<HHH', data, 58)
    assert shsize == 64
    sections = [struct.unpack_from('<IIQQQQIIQQ', data, shoff+n*shsize) for n in range(count)]
    names_data = data[sections[names_index][4]:sections[names_index][4]+sections[names_index][5]]
    names = [names_data[s[0]:].split(b'\0',1)[0].decode() for s in sections]
    sym_index = names.index('.symtab')
    sym_section = sections[sym_index]
    strings_section = sections[sym_section[6]]
    strings = data[strings_section[4]:strings_section[4]+strings_section[5]]
    symbols = []
    for off in range(sym_section[4], sym_section[4]+sym_section[5], 24):
        name, info, other, section, value, size = struct.unpack_from('<IBBHQQ', data, off)
        symbols.append(dict(name=strings[name:].split(b'\0',1)[0].decode(), info=info, section=section, value=value, size=size))
    probe = next(s for s in symbols if s['name']=='mtu3_probe')
    text = sections[probe['section']]
    begin = text[4]+probe['value']
    code = data[begin:begin+probe['size']]
    instructions = [dict(address=hex(i.address), mnemonic=i.mnemonic, operands=i.op_str) for i in Cs(CS_ARCH_ARM64,CS_MODE_ARM).disasm(code,probe['value'])]
    relocations = []
    for section in sections:
        if section[1]!=4 or section[7]!=probe['section']:
            continue
        assert section[9]==24
        for off in range(section[4], section[4]+section[5], 24):
            location, info, addend = struct.unpack_from('<QQq',data,off)
            if probe['value'] <= location < probe['value']+probe['size']:
                relocations.append(dict(address=hex(location), symbol=symbols[info>>32]['name'], type=info&0xffffffff, addend=addend))
    output = PROJECT / 'docs/stock-mtu3-probe-audit.json'
    output.write_text(json.dumps(dict(module_sha256=hashlib.sha256(data).hexdigest(), probe=probe, file_offset=begin, entry_words=[hex(x) for x in struct.unpack_from('<4I',data,begin)], instructions=instructions, relocations=relocations, phone_contacted=False, limits='Static stock-module audit locates code and potential calls, not a runtime failure or blocked instruction.'),indent=2)+'\n')
    calls=[item for item in relocations if item['type']==283 and item['symbol'] and not item['symbol'].startswith('_dev_')]
    print(json.dumps(dict(report=str(output), probe=probe, file_offset=begin, entry=instructions[:4], calls=calls),indent=2))


if __name__=='__main__':
    main()
