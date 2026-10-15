"""Exercise radio-clock guards with isolated filesystem fixtures; no phone/hardware access."""
import hashlib,json,os,shutil,subprocess,sys,time
from pathlib import Path
R=Path(__file__).resolve().parent.parent;P=R/'linux-port';sys.path.insert(0,str(P))
from audit_ufs_reset_supplier import fdt_nodes
SOURCE=P/'radio-clock-guard.sh';AUDIT=json.loads((P/'docs/stock-radio-clock-audit.json').read_text())
nodes=fdt_nodes((P/'artifacts/stock-runtime-dtb-overlay5/stock-merged.dtb').read_bytes())
out=R/'tools/test-artifacts'/('radio-clock-guard-'+str(time.time_ns()));out.mkdir()
fake=out/'busybox';fake.write_text("""#!/usr/bin/python3
import os,pathlib,subprocess,sys
r=pathlib.Path(os.environ['FIXTURE']);mode=os.environ['MODE'];a=sys.argv[1:]
def link(p,target):
 p.parent.mkdir(parents=True,exist_ok=True);p.symlink_to(target)
if a[0]=='insmod':
 with (r/'loads').open('a') as f:f.write(a[1]+'\\n')
 if a[1].endswith('mt6685-core.ko'):
  if mode=='mfd-load-failed':sys.exit(1)
  if mode!='mfd-bind-missing':link(r/'spmi/devices/mfd/driver',r/'spmi/drivers/mt6685')
  dev=r/'platform/devices/clock';dev.mkdir(parents=True)
  target=r/'dt/spmi@1c015000/mt6685_mfd/mt6685_clock_buffer'
  if mode=='clock-wrong-node':
   target=r/'dt/wrong-clock';target.mkdir();(target/'compatible').write_bytes(b'mediatek,clock_buffer\\0')
  link(dev/'of_node',target)
  if mode=='clock-busy':link(dev/'driver',r/'platform/drivers/foreign')
  if mode=='extra-platform-id':
   d=r/'platform/devices/extra';d.mkdir();(d/'modalias').write_text('platform:mtk-srclken-rc\\n')
 elif a[1].endswith('clkbuf.ko'):
  if mode=='clock-load-failed':sys.exit(1)
  if mode!='clock-bind-missing':link(r/'platform/devices/clock/driver',r/'platform/drivers/mtk-clock-buffer')
  if mode!='rc-bind-missing':link(r/'platform/devices/rc/driver',r/'platform/drivers/mtk-srclken-rc')
 else:sys.exit(99)
else:sys.exit(subprocess.run(a).returncode)
""");fake.chmod(0o755)
specs=[('success',0,2),('preloaded',36,0),('missing-map',36,0),('empty-map',36,0),('bad-property',36,0),('wrong-mfd-node',36,0),('duplicate-mfd',36,0),('mfd-busy',36,0),('rc-busy',36,0),('mfd-load-failed',37,1),('mfd-bind-missing',37,1),('clock-wrong-node',38,1),('clock-busy',38,1),('extra-platform-id',38,1),('clock-load-failed',38,2),('clock-bind-missing',38,2),('rc-bind-missing',39,2)]
results=[]
for mode,expected,count in specs:
 f=out/mode;f.mkdir();(f/'module').mkdir();(f/'spmi/devices').mkdir(parents=True);(f/'platform/devices').mkdir(parents=True)
 for bus,name in [('spmi','mt6685'),('platform','mtk-clock-buffer'),('platform','mtk-srclken-rc'),('platform','foreign')]: (f/bus/'drivers'/name).mkdir(parents=True)
 for row in AUDIT['runtime_property_checks']:
  path=f/'dt'/row['node'].lstrip('/')/row['property'];path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(nodes[row['node']][row['property']])
 prop=f/'properties';prop.write_text(''.join(r['node']+' '+r['property']+' '+r['sha256']+'\n' for r in AUDIT['runtime_property_checks']))
 for filename in ['mt6685-core.ko','clkbuf.ko']:shutil.copyfile(P/'artifacts/stock-cph2493-August-eu-ota/vendor-ramdisk-unpacked/lib/modules'/filename,f/filename)
 for bus,name,node in [('spmi','mfd',AUDIT['targets']['mediatek,mt6685']),('platform','rc',AUDIT['targets']['mediatek,srclken-rc'])]:
  d=f/bus/'devices'/name;d.mkdir();(d/'of_node').symlink_to(f/'dt'/node.lstrip('/'))
 if mode=='preloaded':(f/'module/clkbuf').mkdir()
 if mode=='missing-map':prop.unlink()
 if mode=='empty-map':prop.write_text('')
 if mode=='bad-property':(f/'dt/srclken-rc@1c00d000/wifi-ctl').write_bytes(b'wrong\0')
 if mode=='wrong-mfd-node':
  (f/'spmi/devices/mfd/of_node').unlink();d=f/'dt/wrong-mfd';d.mkdir();(d/'compatible').write_bytes(b'mediatek,mt6685\0');(f/'spmi/devices/mfd/of_node').symlink_to(d)
 if mode=='duplicate-mfd':
  d=f/'spmi/devices/duplicate';d.mkdir();(d/'of_node').symlink_to(f/'dt'/AUDIT['targets']['mediatek,mt6685'].lstrip('/'))
 if mode=='mfd-busy':(f/'spmi/devices/mfd/driver').symlink_to(f/'spmi/drivers/mt6685')
 if mode=='rc-busy':(f/'platform/devices/rc/driver').symlink_to(f/'platform/drivers/foreign')
 source=SOURCE.read_text().replace('/sys/firmware/devicetree/base',str(f/'dt')).replace('/sys/bus/spmi',str(f/'spmi')).replace('/sys/bus/platform',str(f/'platform')).replace('/sys/module',str(f/'module')).replace('/etc/lynx/radio-clock-properties',str(prop))
 # sha reads actual frozen module bytes; fake insmod sees original fixed names.
 for filename in ['mt6685-core.ko','clkbuf.ko']:
  source=source.replace('$BB sha256sum /lib/modules/'+filename,'$BB sha256sum '+str(f/filename))
 script=f/'test.sh';script.write_text("BB='"+str(fake)+"'\nlog() { printf '%s\\n' \"$*\"; }\n"+source+'\nlynx_radio_clock_load\n');p=subprocess.run(['sh',str(script)],env=dict(os.environ,FIXTURE=str(f),MODE=mode),capture_output=True,text=True,timeout=20)
 (f/'stdout').write_text(p.stdout);(f/'stderr').write_text(p.stderr)
 loads=(f/'loads').read_text().splitlines() if (f/'loads').exists() else []
 assert p.returncode==expected and len(loads)==count,(mode,p.returncode,loads,p.stdout,p.stderr)
 if count==2:assert loads==['/lib/modules/mt6685-core.ko','/lib/modules/clkbuf.ko']
 results.append({'case':mode,'exit_code':p.returncode,'loads':loads})
report={'passed':True,'source_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),'cases':results,'phone_contacted':False,'host_hardware_access':False}
path=out/'result.json';path.write_text(json.dumps(report,indent=2)+'\n');print(path)
