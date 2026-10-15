"""Test bounded record selection/checksum/crash clues with isolated files."""
import hashlib,json,os,subprocess,time
from pathlib import Path
R=Path(__file__).resolve().parent.parent;P=R/'linux-port';SOURCE=P/'lynx-retained-log-runtime.sh'
reference=json.loads((P/'artifacts/busybox-retained-log-query-v1/build-validation.json').read_text())['reference_ufs_token']
payload=f'LXDG1 {reference} 00000001 0000000a 0200 0029';frame=payload+' '+hashlib.sha256(payload.encode()).hexdigest()+'\n';bad=payload+' '+'0'*64+'\n'
crash='Kernel panic - not syncing: fixture\nCFI failure at fixture\nCall trace:\n ufs_mtk_init+0x10/0x20\n'
out=R/'tools/test-artifacts'/('retained-log-control-'+str(time.time_ns()));out.mkdir()
fake=out/'busybox';fake.write_text('''#!/usr/bin/python3
import os,pathlib,shutil,time,sys,subprocess
r=pathlib.Path(os.environ['FIXTURE']);a=sys.argv[1:];mode=os.environ['MODE']
if a[0]=='mv':shutil.move(a[1],a[2])
elif a[0]=='sleep':
 time.sleep(.002);p=r/'run/lynx/module-progress';code=int(p.read_text()) if p.exists() else -1
 if (r/'target').exists():(r/'uptime').write_text((r/'target').read_text()+'.00 0\\n')
 elif code==int(os.environ['FIELD']):(r/'uptime').write_text('90.00 0\\n')
elif a[0]=='insmod':
 if mode=='base-pending':
  while not (r/'release').exists():time.sleep(.002)
  sys.exit(1)
 if mode=='base-failed':sys.exit(1)
elif a[0]=='head' and mode=='query-pending':
 while not (r/'release').exists():time.sleep(.002)
 sys.exit(1)
else:sys.exit(subprocess.run(a).returncode)
''');fake.chmod(0o755)
reset=out/'reset';reset.write_text('''#!/usr/bin/python3
import os,pathlib
r=pathlib.Path(os.environ['FIXTURE'])
with (r/'resets').open('a') as f:f.write('reset\\n')
(r/'release').touch()
''');reset.chmod(0o755)
specs=[('empty',0,[]),('unrelated',1,['ordinary log\n']),('invalid-checksum',3,[bad]),('valid-frame',7,[frame]),('matching-crash',63,[frame+crash]),('no-cross-file-mixing',7,[crash,frame]),('prefer-valid-reference',7,[bad+crash,frame]),('eight-file-limit',1,['ordinary\n']*8+[frame+crash]),('one-megabyte-limit',1,['N'*1048576+frame+crash]),('base-failed',66,[]),('base-pending',64,[]),('query-pending',65,['pending'])]
cases=[]
for mode,expected,records in specs:
    folder=out/mode;run=folder/'run/lynx';run.mkdir(parents=True);(run/'boot.log').touch();(folder/'pstore').mkdir();(folder/'uptime').write_text('0.00 0\n');(folder/'count').write_text('34\n');(folder/'modules.load').write_text(''.join('mod'+str(i)+'.ko\n' for i in range(1,35)));(folder/'reference').write_text(reference+'\n')
    for i,data in enumerate(records):(folder/'pstore'/('record-'+str(i))).write_text(data)
    source=SOURCE.read_text().replace('/sys/fs/pstore',str(folder/'pstore')).replace('/proc/last_kmsg',str(folder/'last_kmsg')).replace('/etc/lynx/reference-ufs-token',str(folder/'reference')).replace('/etc/lynx/progress-count',str(folder/'count')).replace('/etc/lynx/progress-modules.load',str(folder/'modules.load')).replace('/proc/uptime',str(folder/'uptime')).replace('/run/lynx',str(run)).replace('/bin/boot-proof-reboot',str(reset))
    assert '/sys/fs/pstore' not in source and '/proc/last_kmsg' not in source
    log=f"log() {{ printf '%s\\n' \"$*\"; case \"$*\" in 'MODULE_PROGRESS_FIELD code='*) printf '%s' \"$progress_delay\" > '{folder}/target';; esac; }}\n"
    script=folder/'test.sh';script.write_text(f"BB='{fake}'\nlynx_diag_init() {{ return 1; }}\n"+log+source+'\nlynx_module_progress\n')
    result=subprocess.run(['sh',str(script)],env=dict(os.environ,FIXTURE=str(folder),MODE=mode,FIELD=str(expected)),capture_output=True,text=True,timeout=30)
    (folder/'stdout').write_text(result.stdout);(folder/'stderr').write_text(result.stderr)
    assert result.returncode==1 and f'MODULE_PROGRESS_FIELD code={expected} ' in result.stdout,(mode,result.stdout,result.stderr)
    assert (folder/'resets').read_text().splitlines()==['reset']
    captures=list((run/'retained').glob('record-*')) if (run/'retained').exists() else []
    assert len(captures)<=8 and all(p.stat().st_size<=1048576 for p in captures),mode
    cases.append({'case':mode,'field':expected,'bounded':True,'one_reset':True})
report={'passed':True,'source_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),'cases':cases,'phone_contacted':False,'host_hardware_access':False}
path=out/'result.json';path.write_text(json.dumps(report,indent=2)+'\n');print(path)
