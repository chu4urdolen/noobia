"""Test harmless help accepted/rejected/absent/pending with host-only fixtures."""
import hashlib,json,os,subprocess,time
from pathlib import Path
R=Path(__file__).resolve().parent.parent;SOURCE=R/'linux-port/lynx-reset-interface-runtime.sh'
out=R/'tools/test-artifacts'/('reset-interface-control-'+str(time.time_ns()));out.mkdir()
fake=out/'busybox';fake.write_text('''#!/usr/bin/python3
import os,pathlib,shutil,time,sys
r=pathlib.Path(os.environ['FIXTURE']);a=sys.argv[1:]
if a[0]=='mv':shutil.move(a[1],a[2])
elif a[0]=='sleep':
 time.sleep(.002)
 p=r/'run/lynx/module-progress';code=int(p.read_text()) if p.exists() else -1
 if (r/'target').exists():(r/'uptime').write_text((r/'target').read_text()+'.00 0\\n')
 elif code==int(os.environ['FIELD']):(r/'uptime').write_text('90.00 0\\n')
else:sys.exit(2)
''');fake.chmod(0o755)
reset=out/'reset';reset.write_text('''#!/usr/bin/python3
import os,pathlib,stat
r=pathlib.Path(os.environ['FIXTURE'])
with (r/'resets').open('a') as f:f.write('reset\\n')
q=r/'interface'
if q.exists() and stat.S_ISFIFO(q.stat().st_mode):
 with q.open() as f:f.read()
''');reset.chmod(0o755)
cases=[]
for mode,expected in [('accepted',0),('rejected',1),('absent',2),('pending',3)]:
    folder=out/mode;run=folder/'run/lynx';run.mkdir(parents=True);(run/'boot.log').touch();(folder/'uptime').write_text('0.00 0\n');(folder/'count').write_text('0\n');(folder/'modules.load').write_text('\n')
    q=folder/'interface'
    if mode=='accepted':q.touch()
    elif mode=='rejected':q.mkdir()
    elif mode=='pending':os.mkfifo(q)
    source=SOURCE.read_text().replace('/proc/sysrq-trigger',str(q)).replace('/etc/lynx/progress-count',str(folder/'count')).replace('/etc/lynx/progress-modules.load',str(folder/'modules.load')).replace('/proc/uptime',str(folder/'uptime')).replace('/run/lynx',str(run)).replace('/bin/boot-proof-reboot',str(reset))
    assert '/proc/sysrq-trigger' not in source
    log=f"log() {{ printf '%s\\n' \"$*\"; case \"$*\" in 'MODULE_PROGRESS_FIELD code='*) printf '%s' \"$progress_delay\" > '{folder}/target';; esac; }}\n"
    script=folder/'test.sh';script.write_text(f"BB='{fake}'\nlynx_diag_init() {{ return 1; }}\n"+log+source+'\nlynx_module_progress\n')
    result=subprocess.run(['sh',str(script)],env=dict(os.environ,FIXTURE=str(folder),FIELD=str(expected)),capture_output=True,text=True,timeout=15)
    (folder/'stdout').write_text(result.stdout);(folder/'stderr').write_text(result.stderr)
    assert result.returncode==1 and f'MODULE_PROGRESS_FIELD code={expected} ' in result.stdout,(mode,result.stdout,result.stderr)
    assert (folder/'resets').read_text().splitlines()==['reset']
    if mode=='accepted':assert q.read_bytes()==b'h'
    cases.append({'mode':mode,'field':expected,'one_ordinary_reset':True})
report={'passed':True,'source_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),'cases':cases,'phone_contacted':False,'host_reset_interface_used':False}
path=out/'result.json';path.write_text(json.dumps(report,indent=2)+'\n');print(path)
