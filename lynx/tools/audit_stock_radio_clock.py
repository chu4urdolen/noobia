"""Exact OF tables/ABI/provider graph for stock MT6685 and clock-buffer modules."""
import hashlib,json,struct,sys
from pathlib import Path
R=Path(__file__).resolve().parent.parent;P=R/'linux-port';sys.path.insert(0,str(P))
from image_formats import elf64,module_metadata,require
from audit_ufs_reset_supplier import fdt_nodes
S=P/'artifacts/stock-cph2493-August-eu-ota';D=S/'vendor-ramdisk-unpacked/lib/modules'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def table(raw,name):
    e=elf64(raw);names=e['sections']['.strtab'];sym=e['sections']['.symtab'];shoff=struct.unpack_from('<Q',raw,40)[0];shsize=struct.unpack_from('<H',raw,58)[0]
    found=[]
    for offset in range(0,len(sym),24):
        index,info,_,section,value,size=struct.unpack_from('<IBBHQQ',sym,offset);label=names[index:names.index(b'\0',index)].decode()
        if label!=name:continue
        require(info&15==1 and size%200==0,'Bad OF table')
        h=struct.unpack_from('<IIQQQQIIQQ',raw,shoff+section*shsize);data=raw[h[4]+value:h[4]+value+size]
        rows=[]
        for n in range(0,size,200):
            r=data[n:n+200];require(not r[:64].rstrip(b'\0'),'Unexpected OF name/type')
            c=r[64:192].split(b'\0')[0].decode()
            if c:rows.append(c)
        found.append(rows)
    require(len(found)==1,'OF table absent/ambiguous')
    return found[0]
paths=[]
for row in json.loads((P/'docs/storage-prefix-dependencies.json').read_text())['module_order']:paths.append(D/row['file'])
for row in json.loads((P/'docs/wifi-module-audit.json').read_text())['modules']:paths.append(Path(row['file']))
known={};names=set()
for path in set(paths):
    raw=path.read_bytes();meta=module_metadata(raw)['values'];names.update(meta.get('name',[]))
    for crc,symbol in struct.iter_unpack('<Q56s',elf64(raw)['sections'].get('__versions',b'')):
        symbol=symbol.split(b'\0')[0];require(symbol not in known or known[symbol]==crc,'Existing shared CRC conflict');known[symbol]=crc
spec={'mt6685-core.ko':{'mt6685_id_table':['mediatek,mt6685']},'clkbuf.ko':{'mtk_clkbuf_of_match':['mediatek,clock_buffer'],'mtk_srclken_rc_of_match':['mediatek,srclken-rc']}}
modules=[]
for filename,tables in spec.items():
    raw=(D/filename).read_bytes();e=elf64(raw);meta=module_metadata(raw)['values']
    require(meta['vermagic']==['5.10.149-android12-9-o-g311738fbb5a8 SMP preempt mod_unload modversions aarch64'],'Kernel mismatch')
    deps={n for value in meta.get('depends',[]) for n in value.split(',') if n}
    require({n.replace('-','_') for n in deps}<={n.replace('-','_') for n in names}|{'clkbuf','mt6685_core'},'Prerequisites absent: '+repr(deps))
    for name,expected in tables.items():require(table(raw,name)==expected,'Extra OF match')
    for crc,symbol in struct.iter_unpack('<Q56s',e['sections'].get('__versions',b'')):
        symbol=symbol.split(b'\0')[0];require(symbol not in known or known[symbol]==crc,'New shared CRC conflict');known[symbol]=crc
    modules.append({'file':filename,'sha256':sha(raw),'metadata':meta,'of_tables':tables,'dependencies':sorted(deps)})
nodes=fdt_nodes((P/'artifacts/stock-runtime-dtb-overlay5/stock-merged.dtb').read_bytes())
compatibles=[b'mediatek,mt6685',b'mediatek,clock_buffer',b'mediatek,srclken-rc']
targets={}
for compatible in compatibles:
    matches=[n for n,p in nodes.items() if compatible in p.get('compatible',b'').split(b'\0')]
    require(len(matches)==1,'Ambiguous DT target')
    target=matches[0];props=nodes[target];require(props.get('status',b'okay\0') in [b'okay\0',b'ok\0'],'Disabled DT target')
    targets[compatible.decode()]=target
require(targets['mediatek,clock_buffer']==targets['mediatek,mt6685']+'/mt6685_clock_buffer','MFD graph differs')
require(nodes[targets['mediatek,srclken-rc']]['wifi-ctl']==b'XO_BBCK2\0','Wi-Fi clock output differs')
checks=[]
for target,properties in [(targets['mediatek,mt6685'],['compatible','reg']),(targets['mediatek,clock_buffer'],['compatible','clkbuf_ctl','mediatek,xo-buf-name','mediatek,xo-buf-support','mediatek,xo-buf-allow-control','mediatek,enable']),(targets['mediatek,srclken-rc'],['compatible','reg','wifi-ctl','ufs-ctl','mediatek,enable']),('/clock_buffer_ctrl',['compatible','pmif','srclken_rc','consys','mediatek,enable'])]:
    for prop in properties:
        require(prop in nodes[target],'Property missing');checks.append({'node':target,'property':prop,'sha256':sha(nodes[target][prop])})
report={'passed':True,'phone_contacted':False,'modules':modules,'targets':targets,'runtime_property_checks':checks,'shared_crc_conflicts':[],'wifi_clock':'XO_BBCK2','limits':'Exact stock binaries/OF tables/ABI/DT. Published source reference not exact binary provenance. Driver binding is not proof that every hardware clock succeeds; runtime guards/ABI tests required before flash.'}
out=P/'docs/stock-radio-clock-audit.json';out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
