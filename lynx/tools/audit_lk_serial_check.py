"""Offline stock LK instruction windows for the observed line1324 warning."""
import hashlib
import json
from pathlib import Path
import struct
from capstone import Cs,CS_ARCH_ARM64,CS_MODE_ARM
from audit_lk_log_strings import ROOT,IMAGE,EXPECTED

def main():
    image=IMAGE.read_bytes()
    if hashlib.sha256(image).hexdigest()!=EXPECTED:raise RuntimeError('Stock LK changed')
    size=struct.unpack_from('<I',image,4)[0];payload=image[512:512+size]
    matches=[]
    md=Cs(CS_ARCH_ARM64,CS_MODE_ARM)
    for offset in range(0,len(payload)-3,4):
        word=struct.unpack_from('<I',payload,offset)[0]
        if word & 0xffe00000==0x52800000 and (word>>5)&0xffff==1324 and word&31<8:
            start=max(0,offset-160);end=min(len(payload),offset+256)
            matches.append(dict(relative_offset=hex(offset),instructions=[
                dict(address=hex(i.address),mnemonic=i.mnemonic,operands=i.op_str)
                for i in md.disasm(payload[start:end],0x100000+start)]))
    strings=[]
    for marker in [b'efuse_Serial_verify',b'mt_boot_init']:
        start=0
        while True:
            pos=payload.find(marker,start)
            if pos<0:break
            strings.append(dict(marker=marker.decode(),relative_offset=hex(pos),
                                following=payload[pos:pos+150].split(b'\0',1)[0].decode('ascii','backslashreplace')))
            start=pos+1
    report=dict(phone_contacted=False,stock_lk_sha256=EXPECTED,analysis_base='0x100000',
                line_number_windows=matches,strings=strings,
                limits='A matching debug line immediate alone is not a symbol or complete control-flow proof.')
    output=ROOT/'linux-port/docs/lk-serial-check-audit.json'
    output.write_text(json.dumps(report,indent=2)+'\n')
    print('Instruction windows:',len(matches),'preserved:',output)
    for match in matches:
        for i in match['instructions']:print(i['address'],i['mnemonic'],i['operands'])

if __name__=='__main__':main()
