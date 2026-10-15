"""Save stock Wi-Fi power/probe disassembly and relocations for offline review."""
import hashlib,json,struct,sys,time
from pathlib import Path
from capstone import Cs,CS_ARCH_ARM64,CS_MODE_ARM
R=Path(__file__).resolve().parent.parent;P=R/'linux-port'
sys.path.insert(0,str(P))
from image_formats import elf64,require
D=P/'artifacts/stock-cph2493-August-eu-ota/wifi-reference/vendor-dlkm-unpacked/lib/modules'
out=P/'docs'/('wifi-power-binary-'+str(time.time_ns()));out.mkdir(mode=0o700)
report={'phone_contacted':False,'modules':{},'limits':'Static exact-binary evidence only; relocations are unresolved until module loading. No patches or handset commands.'}
for name,wanted in {
    'wmt_chrdev_wifi_connac2.ko':['mtk_wcn_wlan_func_ctrl','mtk_wland_thread_main'],
    'wlan_drv_gen4m_6983.ko':['wlanProbe','wlanAdapterStart','wf_pwr_on_consys_mcu'],
}.items():
    raw=(D/name).read_bytes();parsed=elf64(raw);require(parsed['machine']==183,'Wrong architecture')
    shoff=struct.unpack_from('<Q',raw,40)[0];step,count,names_idx=struct.unpack_from('<3H',raw,58)
    sections=[struct.unpack_from('<IIQQQQIIQQ',raw,shoff+i*step) for i in range(count)]
    strings=parsed['sections']['.strtab'];symraw=parsed['sections']['.symtab'];symbols=[]
    for pos in range(0,len(symraw),24):
        n,info,other,sec,value,size=struct.unpack_from('<IBBHQQ',symraw,pos)
        symbols.append({'name':strings[n:strings.index(b'\0',n)].decode(),'info':info,'section':sec,'offset':value,'size':size})
    record={'sha256':hashlib.sha256(raw).hexdigest(),'functions':{}};report['modules'][name]=record
    for label in wanted:
        matches=[s for s in symbols if s['name']==label and s['info']&15==2 and s['size']]
        require(len(matches)==1,'Missing/ambiguous function '+label);s=matches[0];h=sections[s['section']]
        code=raw[h[4]+s['offset']:h[4]+s['offset']+s['size']];relocs=[]
        for rh in sections:
            if rh[1]!=4 or rh[7]!=s['section']:continue
            for pos in range(rh[4],rh[4]+rh[5],24):
                off,info,addend=struct.unpack_from('<QQq',raw,pos)
                if s['offset']<=off<s['offset']+s['size']:
                    target=symbols[info>>32]
                    relocs.append({'offset':off,'type':info&0xffffffff,'symbol':target['name'],'addend':addend})
        by_offset={r['offset']:r for r in relocs};lines=[]
        for ins in Cs(CS_ARCH_ARM64,CS_MODE_ARM).disasm(code,s['offset']):
            suffix=' ; '+json.dumps(by_offset[ins.address]) if ins.address in by_offset else ''
            lines.append(f'{ins.address:08x} {ins.bytes.hex():8} {ins.mnemonic} {ins.op_str}'+suffix)
        require(len(lines)*4==len(code),'Incomplete instruction decode')
        path=out/(name+'-'+label+'.txt');path.write_text('\n'.join(lines)+'\n')
        record['functions'][label]={**s,'code_sha256':hashlib.sha256(code).hexdigest(),'assembly':str(path),'relocations':relocs}
(out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(out/'result.json')
