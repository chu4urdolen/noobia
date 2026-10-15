"""Prepare stock thermal/power inputs for manual diagnostics AFTER pinned SSH.

Offline only. No image changes, phone access, module loading or hold removal.
"""
import argparse,gzip,hashlib,io,json,os,re,struct,sys,tarfile,time
from pathlib import Path
R=Path(__file__).resolve().parent.parent;P=R/'linux-port';sys.path.insert(0,str(P))
from image_formats import module_metadata,elf64,require
from audit_ufs_reset_supplier import fdt_nodes
S=P/'artifacts/stock-cph2493-August-eu-ota'
GROUPS={'soc-temperature':'soc_temp_lvts.ko','cpu-frequency':'mediatek-cpufreq-hw.ko','board-temperature':'thermal-generic-adc.ko','thermal-integration':'thermal_interface.ko','battery':'mt6375-battery.ko','charging':'oplus_chg.ko','typec':'tcpc_mt6375.ko'}
def norm(s):return s.removesuffix('.ko').replace('-','_')
def sha(data):return hashlib.sha256(data).hexdigest()
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--sensor-trial',action='store_true',help='Prepare reviewed sensor-only supervised trial; never connect or load');args=parser.parse_args()
 os.umask(0o077);out=P/'artifacts'/('thermal-ssh-pack-'+str(time.time_ns()));out.mkdir(mode=0o700)
 inventory=(R/'logs/live-inventory-1792098110330311623/inventory.stdout').read_text();loaded={line.split()[0] for line in inventory.split('MODULES\n',1)[1].splitlines() if re.match(r'^\w+ \d+ ',line)}
 index={}
 for root in [S/'vendor-ramdisk-unpacked/lib/modules',S/'wifi-reference/vendor-dlkm-unpacked/lib/modules']:
  for f in root.glob('*.ko'):index.setdefault(norm(f.name),f)
 metadata={};blobs={};versions={};conflicts=[];selected=set();groups={}
 def add(name,order,active):
  name=norm(name);require(name in index,'Dependency unavailable: '+name);require(name not in active,'Dependency cycle: '+name)
  if name in order:return
  active.add(name)
  if name not in metadata:
   raw=index[name].read_bytes();m=module_metadata(raw)['values'];require(m['vermagic']==['5.10.149-android12-9-o-g311738fbb5a8 SMP preempt mod_unload modversions aarch64'],'Kernel mismatch: '+name);metadata[name]=m;blobs[name]=raw
  for child in ','.join(metadata[name].get('depends',[])).split(','):
   if child:add(child,order,active)
  active.remove(name);order.append(name);selected.add(name)
 for group,target in GROUPS.items():
  order=[]
  if group=='soc-temperature':add('nvmem_mtk-devinfo',order,set())
  add(target,order,set());groups[group]={'target':norm(target),'full_dependency_order':order,'missing_in_saved_boot':[n for n in order if n not in loaded],'automatic_loading':False,'review_only':group!='soc-temperature' if args.sensor_trial else group not in ['soc-temperature','cpu-frequency']}
 # Compare overlapping imported symbol CRCs with all saved-live stock modules.
 for name in sorted(selected|loaded):
  if name not in index:continue
  raw=blobs.get(name) or index[name].read_bytes()
  for crc,symbol in struct.iter_unpack('<Q56s',elf64(raw)['sections'].get('__versions',b'')):
   symbol=symbol.split(b'\0')[0].decode()
   if symbol in versions and versions[symbol]!=crc:conflicts.append({'module':name,'symbol':symbol})
   versions[symbol]=crc
 require(not conflicts,'Shared ABI CRC conflicts')
 dt=(P/'artifacts/stock-runtime-dtb-overlay5/stock-merged.dtb').read_bytes();nodes=fdt_nodes(dt)
 matches={}
 for name in ['soc_temp_lvts','mediatek_cpufreq_hw','oplus_omrg','nvmem_mtk_devinfo']:
  raw=blobs[name];aliases=metadata[name].get('alias',[]);compat={a.split('*C',1)[1].removesuffix('C*') for a in aliases if a.startswith('of:') and '*C' in a}
  # Some stock modules omit aliases; preserve matching DT literals as candidates.
  for props in nodes.values():
   for c in props.get('compatible',b'').split(b'\0'):
    if c and c+b'\0' in raw:compat.add(c.decode())
  found=[]
  for node,props in nodes.items():
   if compat.intersection(c.decode() for c in props.get('compatible',b'').split(b'\0') if c):
    found.append({'node':node,'status':props.get('status',b'okay\0').rstrip(b'\0').decode(),'compatible':props['compatible'].rstrip(b'\0').decode().split('\0'),'property_hashes':{k:sha(v) for k,v in props.items() if k in ['compatible','reg','clocks','clock-names','interrupts','nvmem-cells','nvmem-cell-names','status']}})
  matches[name]=found
 require(matches['soc_temp_lvts'],'No matching stock sensor DT node')
 require(matches['nvmem_mtk_devinfo'],'Calibration provider DT node missing')
 modules={n:{'file':index[n].name,'source':str(index[n].relative_to(S)),'sha256':sha(blobs[n]),'bytes':len(blobs[n]),'srcversion':metadata[n].get('srcversion',[]),'depends':[norm(c) for c in ','.join(metadata[n].get('depends',[])).split(',') if c],'already_loaded_in_saved_boot':n in loaded} for n in sorted(selected)}
 manifest={'kernel_release':'5.10.149-android12-9-o-g311738fbb5a8','baseline_image_sha256':'5ce2dbf8a7c132fa7e31f6be70aa76f83afe8c293e2cd5f02251a532486fd851','groups':groups,'modules':modules,'shared_symbol_crc_conflicts':conflicts,'stock_merged_dt_sha256':sha(dt),'device_tree_matches':matches,'automatic_loading':False,'phone_contacted':False,'flash_performed':False,'live_trial_eligible':False,'limits':'Preparation only. Exact stock module ABI and candidate DT matches are not physical probe or heat-safety proof. Battery/charging/integration groups remain review-only. Global safety hold stays active.'}
 manifest['live_trial_eligible']=bool(args.sensor_trial)
 manifest['trial_scope']=['soc-temperature'] if args.sensor_trial else []
 manifest['device_tree_provider_prerequisites']=['clk_mt6983','reset_ti_syscon','oplus_project']
 minimum=0
 for node in ['/efuse@11ee0000/data1','/efuse@11ee0000/data2','/efuse@11ee0000/data3']:
  offset,size=struct.unpack('>II',nodes[node]['reg']);minimum=max(minimum,offset+size)
 manifest['devinfo_min_bytes']=minimum
 files={'manifest.json':json.dumps(manifest,indent=2).encode()+b'\n','thermal-step.sh':(P/'thermal-step.sh').read_bytes(),'ALLOWED-STAGES':b'soc-temperature\n' if args.sensor_trial else b'soc-temperature\ncpu-frequency\n','DEVINFO-MIN-BYTES':(str(minimum)+'\n').encode()}
 if not args.sensor_trial:files['REVIEW-HOLD']=b'Preparation only. Hardware remains off; thermal safety review required.\n'
 checks={}
 for rows in matches.values():
  for row in rows:
   for prop,digest in row['property_hashes'].items():checks[row['node'].lstrip('/')+'/'+prop]=digest
 for node in ['/efuse@11ee0000/data1','/efuse@11ee0000/data2','/efuse@11ee0000/data3']:
  checks[node.lstrip('/')+'/reg']=sha(nodes[node]['reg'])
 files['DT-SHA256SUMS']=''.join(digest+'  '+name+'\n' for name,digest in sorted(checks.items())).encode()
 for n in modules:files['modules/'+index[n].name]=blobs[n]
 for group,row in groups.items():
  if not row['review_only']:
   files['plans/'+group+'.list']=''.join(n+' '+modules[n]['file']+'\n' for n in row['full_dependency_order']).encode()
 files['SHA256SUMS']=''.join(sha(data)+'  '+name+'\n' for name,data in sorted(files.items())).encode()
 memory=io.BytesIO()
 with tarfile.open(fileobj=memory,mode='w',format=tarfile.USTAR_FORMAT) as tar:
  for name,data in sorted(files.items()):
   entry=tarfile.TarInfo(name);entry.size=len(data);entry.mode=0o700 if name.endswith('.sh') else 0o600;entry.mtime=0;tar.addfile(entry,io.BytesIO(data))
 archive=gzip.compress(memory.getvalue(),mtime=0);(out/'thermal-ssh-pack.tar.gz').write_bytes(archive);(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');report={'prepared':True,'archive_sha256':sha(archive),'archive_bytes':len(archive),'modules':len(modules),'groups':{n:len(g['missing_in_saved_boot']) for n,g in groups.items()},'phone_contacted':False,'flash_performed':False,'live_trial_eligible':bool(args.sensor_trial)};(out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(out/'result.json');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
