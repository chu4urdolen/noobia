"""Offline virtual-clock supervisor outcomes; all reset calls are fixtures."""
import hashlib,json,os,subprocess,time
from pathlib import Path
R=Path(__file__).resolve().parent.parent;SOURCE=R/'linux-port/lynx-ufs-trace-probe-runtime.sh'
def main():
    out=R/'tools/test-artifacts'/('ufs-trace-probe-control-'+str(time.time_ns()));out.mkdir()
    fake=out/'busybox';fake.write_text('''#!/usr/bin/python3
import os,pathlib,shutil,sys,time
r=pathlib.Path(os.environ['FIXTURE']);a=sys.argv[1:];mode=os.environ['MODE'];expected=int(os.environ['FIELD'])
if a[0]=='sleep':
 time.sleep(.002)
 state=r/'run/lynx/ufs-registration'
 if (r/'target').exists():(r/'uptime').write_text((r/'target').read_text()+'.00 0\\n')
 elif state.exists() and int(state.read_text())==expected:(r/'uptime').write_text('90.00 0\\n')
elif a[0]=='mv':shutil.move(a[1],a[2])
elif a[0]=='insmod':
 if mode=='prefix-fail' and a[1].endswith('/blocktag.ko'):sys.exit(1)
 if a[1].endswith('/ufs-mediatek-mod.ko'):
  if mode=='module-fail':sys.exit(1)
  if mode=='pending':
   while not (r/'release').exists():time.sleep(.002)
   sys.exit(1)
else:sys.exit(2)
''');fake.chmod(0o755)
    reset=out/'reset';reset.write_text('''#!/usr/bin/python3
import os,pathlib
r=pathlib.Path(os.environ['FIXTURE'])
with (r/'resets').open('a') as f:f.write('reset\\n')
(r/'release').touch()
''');reset.chmod(0o755)
    specs=[('success',0),('guard-fail',1),('module-fail',2),('pending',3),('prefix-fail',4),('trace-fail',6),('write-fail',7),('unbound',8),('clear-fail',9)]
    cases=[]
    for name,expected in specs:
        folder=out/name;run=folder/'run/lynx';run.mkdir(parents=True);(run/'boot.log').touch();(folder/'uptime').write_text('0.00 0\n')
        modules=folder/'modules';modules.write_text(''.join('mod'+str(i)+'.ko\n' for i in range(1,40))+'blocktag.ko\n')
        source=SOURCE.read_text().replace('/proc/uptime',str(folder/'uptime')).replace('/run/lynx',str(run)).replace('/etc/lynx/progress-modules.load',str(modules)).replace('/bin/boot-proof-reboot',str(reset))
        functions="lynx_diag_init() { return 1; }\nlynx_ufs_registration_guard() { return "+('1' if name=='guard-fail' else '0')+"; }\nlynx_ufs_guarded_probe() { return "+str(expected if expected in [0,6,7,8,9] else 0)+"; }\n"
        log="log() { printf '%s\\n' \"$*\"; case \"$*\" in 'UFS_REGISTRATION_FIELD code='*) printf '%s' \"$ufs_delay\" > '"+str(folder/'target')+"';; esac; }\n"
        script=folder/'test.sh';script.write_text("BB='"+str(fake)+"'\n"+functions+log+source+'\nlynx_ufs_registration\n')
        result=subprocess.run(['sh',str(script)],env=dict(os.environ,FIXTURE=str(folder),MODE=name,FIELD=str(expected)),capture_output=True,text=True,timeout=20)
        (folder/'stdout').write_text(result.stdout);(folder/'stderr').write_text(result.stderr)
        assert result.returncode==1 and f'UFS_REGISTRATION_FIELD code={expected} ' in result.stdout,(name,result.stdout,result.stderr)
        assert (folder/'resets').read_text().splitlines()==['reset']
        assert int((folder/'uptime').read_text().split('.')[0])==120+5*expected
        cases.append(dict(case=name,field=expected,one_reset=True))
    report=dict(passed=True,cases=cases,source_sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),phone_contacted=False,limits='Actual shell control flow with simulated insmod, probe function and time. Native guard/trace paths checked separately.')
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(out/'result.json')
if __name__=='__main__':main()
