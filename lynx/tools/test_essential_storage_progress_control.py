"""Verify pending/failed clock insertion checkpoints and one reset, offline."""
import hashlib,json,os,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent;SOURCE=ROOT/'linux-port/lynx-essential-storage-progress-runtime.sh'
def main():
    out=ROOT/'tools/test-artifacts'/('essential-storage-progress-control-'+str(time.time_ns()));out.mkdir()
    fake=out/'busybox'
    fake.write_text('''#!/usr/bin/python3
import os,pathlib,shutil,sys,time
r=pathlib.Path(os.environ['FIXTURE']);a=sys.argv[1:];expected=int(os.environ['FIELD']);mode=os.environ['MODE'];index=int(os.environ['INDEX'])
if a[0]=='sleep':
 time.sleep(.002);phase=r/'run/lynx/module-progress'
 code=int(phase.read_text()) if phase.exists() else -1
 if (r/'target').exists():(r/'uptime').write_text((r/'target').read_text()+'.00 0\\n')
 elif code==expected:(r/'uptime').write_text('90.00 0\\n')
elif a[0]=='mv':shutil.move(a[1],a[2])
elif a[0]=='insmod':
 n=int(pathlib.Path(a[1]).name[3:].split('.')[0])
 if mode=='pending' and n==index:
  while not (r/'release').exists():time.sleep(.002)
  sys.exit(1)
 if mode=='failed' and n==index:sys.exit(1)
else:sys.exit(2)
''');fake.chmod(0o755)
    reset=out/'reset';reset.write_text('''#!/usr/bin/python3
import os,pathlib
r=pathlib.Path(os.environ['FIXTURE'])
with (r/'resets').open('a') as f:f.write('reset\\n')
(r/'release').touch()
''');reset.chmod(0o755)
    specs=[('success','success',0,0),('first-base-failure','failed',1,85)]
    for index in range(1,42):
        specs.extend([('clock-pending-'+str(index),'pending',index,index),('clock-failed-'+str(index),'failed',index,index+84)])
    cases=[]
    for name,mode,index,expected in specs:
        folder=out/name;run=folder/'run/lynx';run.mkdir(parents=True);(run/'boot.log').touch();(folder/'uptime').write_text('0.00 0\n')
        (folder/'count').write_text('41\n')
        modules=folder/'modules.load';modules.write_text(''.join('mod'+str(n)+'.ko\n' for n in range(1,42)))
        source=SOURCE.read_text().replace('/etc/lynx/progress-count',str(folder/'count')).replace('/proc/uptime',str(folder/'uptime')).replace('/run/lynx',str(run)).replace('/etc/lynx/progress-modules.load',str(modules)).replace('/bin/boot-proof-reboot',str(reset))
        log=f'''log() {{ printf '%s\\n' "$*"; case "$*" in 'MODULE_PROGRESS_FIELD code='*) printf '%s' "$progress_delay" > '{folder}/target';; esac; }}
'''
        script=folder/'test.sh';script.write_text(f"BB='{fake}'\nlynx_diag_init() {{ return 1; }}\n"+log+source+'\nlynx_storage_payload_checkpoint() { return 0; }\nlynx_module_progress\n')
        result=subprocess.run(['sh',str(script)],env=dict(os.environ,FIXTURE=str(folder),MODE=mode,INDEX=str(index),FIELD=str(expected)),capture_output=True,text=True,timeout=30)
        (folder/'stdout').write_text(result.stdout);(folder/'stderr').write_text(result.stderr)
        assert result.returncode==1,(name,result.stderr)
        assert (folder/'resets').read_text().splitlines()==['reset'],name
        assert f'MODULE_PROGRESS_FIELD code={expected} ' in result.stdout,(name,result.stdout)
        assert int((folder/'uptime').read_text().split('.')[0])==120+2*expected,name
        cases.append({'case':name,'expected_field':expected,'one_reset':True})
    report={'passed':True,'source_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),'cases':cases,'phone_contacted':False,'real_reboots':False,'limits':'Actual shell checkpoint logic with fake insmod/clock/reset; kernel global stalls cannot be emulated.'}
    path=out/'result.json';path.write_text(json.dumps(report,indent=2)+'\n');print(path)
if __name__=='__main__':main()
