"""Verify the exact stock worker's pre-calibration sleep return address."""
import hashlib,json,struct,sys
from pathlib import Path
R=Path(__file__).resolve().parent.parent;P=R/'linux-port';sys.path.insert(0,str(P))
from image_formats import elf64,require
f=P/'artifacts/stock-cph2493-August-eu-ota/wifi-reference/vendor-dlkm-unpacked/lib/modules/wmt_chrdev_wifi_connac2.ko'
raw=f.read_bytes();digest=hashlib.sha256(raw).hexdigest();require(digest=='96df60a8a34fda03201826f44699b007a871f26e4b7644a1ce692ad7f9c88e56','Stock module changed')
e=elf64(raw);s=e['sections'];names=s['.strtab'];symbols=[]
for n in range(0,len(s['.symtab']),24):
    ix,info,_,sec,off,size=struct.unpack_from('<IBBHQQ',s['.symtab'],n)
    symbols.append({'name':names[ix:names.index(b'\0',ix)].decode(),'section':sec,'offset':off,'size':size,'type':info&15})
def one(name):
    matches=[r for r in symbols if r['name']==name];require(len(matches)==1,'Missing/ambiguous '+name);return matches[0]
worker=one('mtk_wland_thread_main');flag=one('pre_cal_ongoing')
require(worker['offset']==0x48a8 and worker['type']==2 and flag['offset']==52 and flag['type']==1,'Critical symbol differs')
text=s['.text'];require(text[0x4ab4:0x4abc]==bytes.fromhex('8025805200000094'),'Sleep300ms call bytes differ')
require(text[0x4ac8:0x4ad4]==bytes.fromhex('080340391f05007121020054'),'Status byte==1 loop branch differs')
rels={}
shoff=struct.unpack_from('<Q',raw,40)[0];step,count=struct.unpack_from('<2H',raw,58)
for index in range(count):
    h=struct.unpack_from('<IIQQQQIIQQ',raw,shoff+index*step)
    if h[1]!=4 or h[7]!=worker['section']:continue
    for n in range(h[4],h[4]+h[5],24):
        off,info,addend=struct.unpack_from('<QQq',raw,n);rels[off]={'type':info&0xffffffff,'target':symbols[info>>32],'addend':addend}
require(rels[0x4ab8]['type']==283 and rels[0x4ab8]['target']['name']=='msleep','Sleep relocation differs')
for off in [0x4918,0x4ac8]:
    r=rels[off];require(r['target']['section']==flag['section'] and r['target']['offset']+r['addend']==flag['offset'],'Status flag relocation differs')
out=P/'docs/wifi-worker-wait-audit.json';out.write_text(json.dumps({'passed':True,'module_sha256':digest,'worker':worker,'status_flag':flag,'sleep_ms':300,'sleep_call_offset':0x4ab8-worker['offset'],'sleep_return_offset':0x4abc-worker['offset'],'phone_contacted':False,'limits':'Exact static instruction/relocation evidence; observing this saved return frame is consistent with this sleep call, not independent proof of why calibration remains pending.'},indent=2)+'\n');print(out)
