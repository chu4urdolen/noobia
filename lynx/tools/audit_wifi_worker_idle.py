"""Verify normal worker-idle return site; no module modification or phone I/O."""
import hashlib,json,struct,sys
from pathlib import Path
R=Path(__file__).resolve().parent.parent;P=R/'linux-port';sys.path.insert(0,str(P))
from image_formats import elf64,module_metadata,require
D=P/'artifacts/stock-cph2493-August-eu-ota/wifi-reference/vendor-dlkm-unpacked/lib/modules'
raw=(D/'wmt_chrdev_wifi_connac2.ko').read_bytes();require(hashlib.sha256(raw).hexdigest()=='96df60a8a34fda03201826f44699b007a871f26e4b7644a1ce692ad7f9c88e56','Module changed')
e=elf64(raw);s=e['sections'];names=s['.strtab'];symbols=[]
for n in range(0,len(s['.symtab']),24):
    ix,info,_,sec,off,size=struct.unpack_from('<IBBHQQ',s['.symtab'],n);symbols.append({'name':names[ix:names.index(b'\0',ix)].decode(),'section':sec,'offset':off,'size':size,'type':info&15})
worker=[v for v in symbols if v['name']=='mtk_wland_thread_main'];require(len(worker)==1 and worker[0]['offset']==0x48a8,'Worker changed');worker=worker[0]
require(s['.text'][0x4978:0x498c]==bytes.fromhex('680340f91f0940f28101005400feffb500000094'),'Idle wait guard/call bytes changed')
shoff=struct.unpack_from('<Q',raw,40)[0];step,count=struct.unpack_from('<2H',raw,58);rels={}
for i in range(count):
    h=struct.unpack_from('<IIQQQQIIQQ',raw,shoff+i*step)
    if h[1]!=4 or h[7]!=worker['section']:continue
    for n in range(h[4],h[4]+h[5],24):
        off,info,addend=struct.unpack_from('<QQq',raw,n);rels[off]={'type':info&0xffffffff,'target':symbols[info>>32]['name'],'addend':addend}
require(rels[0x4988]['type']==283 and rels[0x4988]['target']=='schedule','Idle schedule target changed')
require(rels[0x4938]['target']=='complete' and rels[0x4978]['target']=='g_ulOnoffFlag','Completion/flag reference changed')
wlan=(D/'wlan_drv_gen4m_6983.ko').read_bytes();meta=module_metadata(wlan)['values']
out=P/'docs/wifi-worker-idle-audit.json';out.write_text(json.dumps({'passed':True,'phone_contacted':False,'worker_module_sha256':hashlib.sha256(raw).hexdigest(),'idle_return_offset':0x498c-worker['offset'],'wlan_module_sha256':hashlib.sha256(wlan).hexdigest(),'wlan_module_metadata':meta,'limits':'Static evidence for the worker event-wait site. A sampled idle stack alone does not prove successful radio initialization; require an independently bound network interface and completed current request before considering another station command.'},indent=2)+'\n');print(out)
