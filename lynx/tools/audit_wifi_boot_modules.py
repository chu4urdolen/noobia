"""Audit matching OTA Wi-Fi dependencies and module ABI records offline."""
import hashlib,json,struct,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent;P=ROOT/'linux-port';sys.path.insert(0,str(P))
from image_formats import module_metadata,elf64
S=P/'artifacts/stock-cph2493-August-eu-ota'
files={};deps={};duplicates=[]
for d in [S/'vendor-ramdisk-unpacked/lib/modules',S/'wifi-reference/vendor-dlkm-unpacked/lib/modules']:
 for line in (d/'modules.dep').read_text().splitlines():
  name,_,v=line.partition(':');deps[Path(name).name]=[Path(x).name for x in v.split()]
 for f in d.glob('*.ko'):
  if f.name in files:duplicates.append({'name':f.name,'identical':files[f.name].read_bytes()==f.read_bytes()})
  files[f.name]=f
roots=['phy-mtk-ufs.ko','ufs-mediatek-mod.ko','cfg80211.ko','connfem.ko','conninfra.ko','wmt_chrdev_wifi_connac2.ko','wlan_drv_gen4m_6983.ko']; order=[];visited=set();active=set()
def canonical(name):
 candidates=[k for k in files if k.replace('-','_')==name.replace('-','_')]
 assert len(candidates)==1,('missing or ambiguous module',name)
 return candidates[0]
def direct(name):
 m=module_metadata(files[name].read_bytes())
 return [canonical(x+'.ko') for x in m['values'].get('depends',[''])[0].split(',') if x]
def visit(name):
 if name in visited:return
 assert name in files,name;assert name not in active,'dependency cycle';active.add(name)
 for child in dict.fromkeys([*deps.get(name,[]),*direct(name)]):visit(child)
 active.remove(name);visited.add(name);order.append(name)
for name in roots:visit(name)
def versions(data):
 section=elf64(data)['sections'].get('__versions',b'');assert len(section)%64==0
 return {name.split(b'\0',1)[0].decode():crc for crc,name in struct.iter_unpack('<Q56s',section)}
reference=(S/'vendor-ramdisk-unpacked/lib/modules/cfg80211.ko').read_bytes();magic=module_metadata(reference)['values']['vermagic'];layout=versions(reference)['module_layout']
records=[];crcs={};conflicts=[]
for name in order:
 f=files[name];data=f.read_bytes();m=module_metadata(data);v=versions(data)
 assert m['values']['vermagic']==magic,(name,'vermagic mismatch');assert v.get('module_layout')==layout,(name,'module layout mismatch')
 modinfo=direct(name)
 assert set(modinfo)<=set(order),(name,'unresolved modinfo dependencies',set(modinfo)-set(order))
 for sym,crc in v.items():
  if sym in crcs and crcs[sym]!=crc:conflicts.append({'symbol':sym,'new_module':name,'crc':crc,'previous_crc':crcs[sym]})
  crcs[sym]=crc
 records.append({'name':name,'file':str(f),'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'vermagic':magic,'scmversion':m['values'].get('scmversion'),'dependencies':deps.get(name,[]),'modinfo_depends':modinfo,'module_layout_crc':hex(v['module_layout']),'symbol_version_count':len(v)})
assert not conflicts,'Conflicting imported symbol versions'
r={'phone_contacted':False,'module_order':order,'modules':records,'duplicates':duplicates,'all_duplicate_bytes_identical':all(x['identical'] for x in duplicates),'imported_symbol_crc_conflicts':conflicts,'module_layout_matches_stock':True,'limits':['External module scmversion differs from kernel scmversion; exact vermagic and shared CRCs are checked instead.','Platform suppliers may extend beyond symbol dependencies.','Matching ABI metadata does not prove successful hardware initialization.']}
(P/'docs/wifi-boot-module-audit.json').write_text(json.dumps(r,indent=2)+'\n'); print(json.dumps({'order':order,'bytes':sum(x['bytes'] for x in records),'shared_crc_conflicts':len(conflicts)},indent=2))
