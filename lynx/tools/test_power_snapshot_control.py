"""Exercise actual metadata query with fixture filesystem/module/reset paths."""
import hashlib,json,os,subprocess,time
from pathlib import Path
R=Path(__file__).resolve().parent.parent;SOURCE=R/'linux-port/lynx-power-snapshot-runtime.sh'
out=R/'tools/test-artifacts'/('power-snapshot-control-'+str(time.time_ns()));out.mkdir()
fake=out/'busybox';fake.write_text('''#!/usr/bin/python3
import os,pathlib,shutil,time,sys
r=pathlib.Path(os.environ['FIXTURE']);a=sys.argv[1:];mode=os.environ['MODE']
if a[0]=='mv':shutil.move(a[1],a[2])
elif a[0]=='sleep':
 time.sleep(.002);p=r/'run/lynx/module-progress';code=int(p.read_text()) if p.exists() else -1
 if (r/'target').exists():(r/'uptime').write_text((r/'target').read_text()+'.00 0\\n')
 elif code==int(os.environ['FIELD']):(r/'uptime').write_text('90.00 0\\n')
elif a[0]=='insmod':
 n=int(pathlib.Path(a[1]).name[3:].split('.')[0])
 if mode=='base-pending' and n==1:
  while not (r/'release').exists():time.sleep(.002)
  sys.exit(1)
 if mode=='base-failed' and n==1:sys.exit(1)
elif a[0]=='mount':
 if mode=='query-pending':
  while not (r/'release').exists():time.sleep(.002)
  sys.exit(1)
 if mode=='debug-failed':sys.exit(1)
 (r/'mounts').write_text('debugfs '+str(r/'debug')+' debugfs rw 0 0\\n')
else:sys.exit(2)
''');fake.chmod(0o755)
reset=out/'reset';reset.write_text('''#!/usr/bin/python3
import os,pathlib
r=pathlib.Path(os.environ['FIXTURE'])
with (r/'resets').open('a') as f:f.write('reset\\n')
(r/'release').touch()
''');reset.chmod(0o755)
cases=[]
specs=[('all-present',15),('controller-unbound',12),('domain-absent',13),('debug-failed',9),('interface-absent',7),('base-failed',16),('base-pending',17),('query-pending',18)]
for mode,expected in specs:
    folder=out/mode;run=folder/'run/lynx';run.mkdir(parents=True);(run/'boot.log').touch();(folder/'uptime').write_text('0.00 0\n');(folder/'count').write_text('34\n');(folder/'modules.load').write_text(''.join('mod'+str(i)+'.ko\n' for i in range(1,35)))
    (folder/'driver').mkdir();(folder/'debug').mkdir();(folder/'mounts').touch()
    if mode!='controller-unbound':(folder/'driver/1c001000.power-controller').symlink_to(folder)
    if mode not in ['controller-unbound','domain-absent','debug-failed']:(folder/'debug/pm_genpd/ufs0').mkdir(parents=True)
    if mode!='interface-absent':(folder/'interface').touch()
    source=SOURCE.read_text().replace('/sys/bus/platform/drivers/mtk-scpsys-mt6983',str(folder/'driver')).replace('/sys/kernel/debug',str(folder/'debug')).replace('/proc/mounts',str(folder/'mounts')).replace('/proc/sysrq-trigger',str(folder/'interface')).replace('/etc/lynx/progress-count',str(folder/'count')).replace('/etc/lynx/progress-modules.load',str(folder/'modules.load')).replace('/proc/uptime',str(folder/'uptime')).replace('/run/lynx',str(run)).replace('/bin/boot-proof-reboot',str(reset))
    assert '/proc/sysrq-trigger' not in source and '/sys/kernel/debug' not in source
    log=f"log() {{ printf '%s\\n' \"$*\"; case \"$*\" in 'MODULE_PROGRESS_FIELD code='*) printf '%s' \"$progress_delay\" > '{folder}/target';; esac; }}\n"
    script=folder/'test.sh';script.write_text(f"BB='{fake}'\nlynx_diag_init() {{ return 1; }}\n"+log+source+'\nlynx_module_progress\n')
    result=subprocess.run(['sh',str(script)],env=dict(os.environ,FIXTURE=str(folder),MODE=mode,FIELD=str(expected)),capture_output=True,text=True,timeout=30)
    (folder/'stdout').write_text(result.stdout);(folder/'stderr').write_text(result.stderr)
    assert result.returncode==1 and f'MODULE_PROGRESS_FIELD code={expected} ' in result.stdout,(mode,result.stdout,result.stderr)
    assert (folder/'resets').read_text().splitlines()==['reset']
    cases.append({'case':mode,'field':expected,'one_ordinary_reset':True})
report={'passed':True,'source_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),'cases':cases,'phone_contacted':False,'host_hardware_access':False}
path=out/'result.json';path.write_text(json.dumps(report,indent=2)+'\n');print(path)
