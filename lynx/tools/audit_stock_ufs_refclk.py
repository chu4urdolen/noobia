"""Disassemble the exact stock reference-clock function and list relocation calls."""
import hashlib,json,struct,sys
from pathlib import Path
from capstone import Cs,CS_ARCH_ARM64,CS_MODE_ARM
R=Path(__file__).resolve().parent.parent;P=R/'linux-port';sys.path.insert(0,str(P))
from image_formats import elf64,require
def main():
    path=P/'artifacts/stock-cph2493-August-eu-ota/vendor-ramdisk-unpacked/lib/modules/ufs-mediatek-mod.ko'
    raw=path.read_bytes();require(hashlib.sha256(raw).hexdigest()=='31e452411297a57a6ed4c31b207c3b4604fa8b55acd95cff6135c680846614a4','Stock module changed')
    parsed=elf64(raw);s=parsed['sections'];names=s['.strtab'];symbols=[]
    for offset in range(0,len(s['.symtab']),24):
        index,info,other,section,value,size=struct.unpack_from('<IBBHQQ',s['.symtab'],offset)
        name=names[index:names.index(b'\0',index)].decode();symbols.append(dict(name=name,info=info,section=section,value=value,size=size))
    shoff=struct.unpack_from('<Q',raw,40)[0];shsize,shcount=struct.unpack_from('<HH',raw,58)
    headers=[struct.unpack_from('<IIQQQQIIQQ',raw,shoff+i*shsize) for i in range(shcount)]
    functions=[row for row in symbols if row['section'] and row['info']&15==2 and row['name'].startswith('ufs_mtk_setup_ref_clk') and row['name']!='ufs_mtk_setup_ref_clk_wait_us']
    require(functions,'Stock reference clock function missing')
    results=[];lines=[]
    for function in functions:
        header=headers[function['section']];start=function['value'];end=start+function['size'];require(end<=header[5],'Function outside section')
        code=raw[header[4]+start:header[4]+end];relocations=[]
        for rh in headers:
            if rh[1]!=4 or rh[7]!=function['section']:continue
            for offset in range(rh[4],rh[4]+rh[5],24):
                address,info,addend=struct.unpack_from('<QQq',raw,offset)
                if start<=address<end:
                    relocations.append(dict(offset=address-start,type=info&0xffffffff,symbol=symbols[info>>32]['name'],addend=addend))
        byaddress={start+row['offset']:row for row in relocations}
        instructions=[];lines.append(function['name']+':')
        for insn in Cs(CS_ARCH_ARM64,CS_MODE_ARM).disasm(code,start):
            row=dict(offset=insn.address-start,mnemonic=insn.mnemonic,operands=insn.op_str,relocation=byaddress.get(insn.address));instructions.append(row)
            lines.append(f"  +0x{row['offset']:04x} {insn.mnemonic:8} {insn.op_str}"+((' <'+row['relocation']['symbol']+'>') if row['relocation'] else ''))
        results.append(dict(function=function,relocations=relocations,instructions=instructions))
    disassembly=P/'docs/stock-ufs-refclk-disassembly.txt';disassembly.write_text('\n'.join(lines)+'\n')
    report=dict(passed=True,module_sha256=hashlib.sha256(raw).hexdigest(),functions=results,disassembly=str(disassembly),phone_contacted=False,limits='Exact compiled function and external call relocations; neither proves where hardware execution stopped nor permits bypassing firmware or acknowledgement checks.')
    out=P/'docs/stock-ufs-refclk-audit.json';out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(report=str(out),functions=[dict(name=x['function']['name'],bytes=x['function']['size'],calls=sorted({r['symbol'] for r in x['relocations'] if r['type']==283})) for x in results]),indent=2))
if __name__=='__main__':main()
