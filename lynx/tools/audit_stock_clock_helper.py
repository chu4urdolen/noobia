"""Verify exact stock clock helper match table, imported CRCs and DT target."""
import hashlib,json,struct,sys
from pathlib import Path
R=Path(__file__).resolve().parent.parent;P=R/'linux-port';sys.path.insert(0,str(P))
from image_formats import elf64,module_metadata,require
from audit_ufs_reset_supplier import fdt_nodes
def main():
    stock=P/'artifacts/stock-cph2493-August-eu-ota';path=stock/'vendor-ramdisk-unpacked/lib/modules/clk-bringup.ko';raw=path.read_bytes();parsed=elf64(raw);meta=module_metadata(raw)['values']
    require(meta['depends']==[''],'Clock helper has additional dependencies')
    require(meta['vermagic']==['5.10.149-android12-9-o-g311738fbb5a8 SMP preempt mod_unload modversions aarch64'],'Clock helper kernel mismatch')
    names=parsed['sections']['.strtab'];symbols=parsed['sections']['.symtab'];shoff=struct.unpack_from('<Q',raw,40)[0];shsize,shcount=struct.unpack_from('<HH',raw,58);tables=[]
    for offset in range(0,len(symbols),24):
        index,info,_,section,value,size=struct.unpack_from('<IBBHQQ',symbols,offset);name=names[index:names.index(b'\0',index)].decode()
        if name!='bring_up_id_table':continue
        require(0<section<shcount and info&15==1 and size%200==0,'Unexpected helper OF table')
        header=struct.unpack_from('<IIQQQQIIQQ',raw,shoff+section*shsize);data=raw[header[4]+value:header[4]+value+size];rows=[]
        for start in range(0,size,200):
            record=data[start:start+200];rows.append(dict(name=record[:32].split(b'\0')[0].decode(),type=record[32:64].split(b'\0')[0].decode(),compatible=record[64:192].split(b'\0')[0].decode()))
        tables.append(rows)
    require(len(tables)==1 and [r['compatible'] for r in tables[0] if r['compatible']]==['mediatek,clk-bring-up','mediatek,clk-post-ao'],'Unexpected clock helper matching')
    require(all(not r['name'] and not r['type'] for r in tables[0]),'Additional OF name/type matching needs review')
    known={};dep=json.loads((P/'docs/storage-prefix-dependencies.json').read_text())
    for row in dep['module_order']:
        module=(stock/'vendor-ramdisk-unpacked/lib/modules'/row['file']).read_bytes();require(hashlib.sha256(module).hexdigest()==row['sha256'],'Audited prerequisite changed')
        for crc,symbol in struct.iter_unpack('<Q56s',elf64(module)['sections']['__versions']):known[symbol.split(b'\0')[0]]=crc
    conflicts=[]
    for crc,symbol in struct.iter_unpack('<Q56s',parsed['sections']['__versions']):
        symbol=symbol.split(b'\0')[0]
        if symbol in known and known[symbol]!=crc:conflicts.append(symbol.decode())
    require(not conflicts,'Clock helper import CRC mismatch')
    nodes=fdt_nodes((P/'artifacts/stock-runtime-dtb-overlay5/stock-merged.dtb').read_bytes());targets={name:props for name,props in nodes.items() if any(c in props.get('compatible',b'').split(b'\0') for c in [b'mediatek,clk-bring-up',b'mediatek,clk-post-ao'])}
    require(list(targets)==['/clkitg/bring-up'],'Unexpected stock helper targets');target=targets['/clkitg/bring-up'];require(target.get('status',b'okay\0')==b'okay\0' and b'mediatek,clk-post-ao' not in target['compatible'],'Unexpected helper mode')
    clockhash=hashlib.sha256(target['clocks']).hexdigest();require(clockhash=='c6c820b927cb362d545b5798b35dec002e60f50805a78d4cc81ad7e90b698e9b','Stock helper clocks changed')
    report=dict(passed=True,module_sha256=hashlib.sha256(raw).hexdigest(),module_metadata=meta,of_match_table=tables[0],imported_crc_conflicts=conflicts,target='/clkitg/bring-up',clock_property_sha256=clockhash,phone_contacted=False,limits='Exact stock helper/ABI and merged-DT target; runtime binding/clock success still unproven. Helper enables only DT-listed clocks using normal APIs and ignores individual clock errors.')
    out=P/'docs/stock-clock-helper-audit.json';out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
