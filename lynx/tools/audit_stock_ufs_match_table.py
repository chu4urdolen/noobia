"""Read the exact stock driver's OF match table, rather than infer from strings."""
import hashlib,json,struct,sys
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent;P=ROOT/'linux-port'
sys.path.insert(0,str(P))
from image_formats import elf64,require


def main():
    module=P/'artifacts/stock-cph2493-August-eu-ota/vendor-ramdisk-unpacked/lib/modules/ufs-mediatek-mod.ko'
    raw=module.read_bytes();parsed=elf64(raw);symbols=parsed['sections']['.symtab'];names=parsed['sections']['.strtab']
    shoff=struct.unpack_from('<Q',raw,40)[0];shsize,shcount=struct.unpack_from('<HH',raw,58)
    candidates=[]
    for offset in range(0,len(symbols),24):
        name_offset,info,_,section,value,size=struct.unpack_from('<IBBHQQ',symbols,offset)
        end=names.find(b'\0',name_offset);require(end>=0,'Invalid symbol name')
        name=names[name_offset:end].decode()
        if name=='ufs_mtk_of_match':
            require(section>0 and section<shcount and info&15==1,'Match table must be a defined ELF object')
            header=struct.unpack_from('<IIQQQQIIQQ',raw,shoff+section*shsize)
            require(value+size<=header[5] and size%200==0,'Unexpected OF match table geometry')
            data=raw[header[4]+value:header[4]+value+size]
            rows=[]
            for start in range(0,size,200):
                # of_device_id: name32,type32,compatible128,data pointer8.
                item=data[start:start+200]
                rows.append({'name':item[:32].split(b'\0')[0].decode(),'type':item[32:64].split(b'\0')[0].decode(),
                             'compatible':item[64:192].split(b'\0')[0].decode()})
            candidates.append({'symbol':name,'size':size,'rows':rows})
    require(len(candidates)==1,'Exact match table not found uniquely')
    actual=[row['compatible'] for row in candidates[0]['rows'] if row['compatible']]
    report={'passed':True,'module_sha256':hashlib.sha256(raw).hexdigest(),'table':candidates[0],
            'expected_live_profile_string':'mediatek,mt8183-ufshci','exact_table_agrees_with_profile':actual==['mediatek,mt8183-ufshci'],
            'phone_contacted':False,'limits':'Static exact stock match-table contents; no live kernel platform_match return captured.'}
    path=P/'docs/stock-ufs-match-table.json';path.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))


if __name__=='__main__':main()
