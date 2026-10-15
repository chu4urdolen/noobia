"""Isolated host fixtures for procfs selection, bounds, ambiguity and classification."""
import hashlib,json,subprocess,time
from pathlib import Path
R=Path(__file__).resolve().parent.parent;P=R/'linux-port';out=R/'tools/test-artifacts'/('wifi-worker-stack-'+str(time.time_ns()));out.mkdir()
fake=out/'busybox';fake.write_text('#!/bin/sh\nexec "$@"\n');fake.chmod(0o755)
capture=(P/'wifi-worker-stack.sh').read_text();parser=(P/'power-stack-parser.sh').read_text();checks=[]
for name,workers,stack,expected in [('absent',0,'',31),('one',1,'x'*32768,0),('ambiguous',2,'stack\n',32),('empty',1,'',33),('missing',1,None,33)]:
    f=out/name;f.mkdir();proc=f/'proc';proc.mkdir();run=f/'run';run.mkdir()
    for n in range(workers):
        d=proc/str(100+n);d.mkdir();(d/'comm').write_text('mtk_wland_threa\n');(d/'status').write_text('State: S\n');(d/'wchan').write_text('hrtimer_nanosleep\n')
        if stack is not None:(d/'stack').write_text(stack)
    d=proc/'999';d.mkdir();(d/'comm').write_text('unrelated\n')
    s=capture.replace('ws_root=/proc','ws_root='+str(proc)).replace('/run/lynx',str(run))
    script=f/'test.sh';script.write_text('BB='+str(fake)+'\n'+s+'\nlynx_capture_wifi_worker_stack\n')
    p=subprocess.run(['sh',str(script)],capture_output=True,text=True,timeout=10)
    assert p.returncode==0 and (run/'wifi-worker-stack-result').read_text().strip()==str(expected),(name,p.stdout,p.stderr)
    if name=='one':assert (run/'wifi-worker-stack').stat().st_size==16384
    checks.append({'case':'capture-'+name,'passed':True})
spec=[('precal',0,'[<0>] mtk_wland_thread_main+0x214/0x450 [wmt_chrdev_wifi_connac2]\n',25),('wrong-offset',0,'mtk_wland_thread_main+0x2140/0x450\n',30),('wrong-symbol',0,'FAKE_mtk_wland_thread_main+0x214/0x450\n',30),('probe',0,'wlanProbe+0x100/0x1400\n',26),('firmware',0,'_request_firmware+0x100/0x400\nwlanProbe+0x100/0x1400\n',27),('power',0,'conninfra_pwr_on+0x50/0x300\nwlanProbe+0x100/0x1400\n',28),('other-wait',0,'wait_for_completion+0x20/0x100\n',29),('unknown',0,'kthread+0x20/0x400\n',30),('absent',31,'',31),('ambiguous',32,'',32),('unreadable',33,'',33),('bad-result',199,'data\n',33),('empty',0,'',33),('no-timeout',0,'msleep+0x10/0x100\n',34)]
for name,status,stack,expected in spec:
    f=out/('parse-'+name);f.mkdir();(f/'wifi-worker-stack-result').write_text(str(status)+'\n');(f/'wifi-worker-stack').write_text(stack)
    source=parser.replace('/run/lynx',str(f));prior=28 if name=='no-timeout' else 25
    script=f/'test.sh';script.write_text('BB='+str(fake)+'\nlynx_power_failure_code() { nt_station_code='+str(prior)+'; }\n'+source+'\nlynx_stack_failure_code\nprintf "%s\\n" "$nt_station_code"\n')
    p=subprocess.run(['sh',str(script)],capture_output=True,text=True,timeout=10)
    assert p.returncode==0 and p.stdout.strip()==str(expected),(name,p.stdout,p.stderr)
    checks.append({'case':'parse-'+name,'passed':True})
path=out/'result.json';path.write_text(json.dumps({'passed':True,'capture_sha256':hashlib.sha256(capture.encode()).hexdigest(),'parser_sha256':hashlib.sha256(parser.encode()).hexdigest(),'checks':checks,'phone_contacted':False},indent=2)+'\n');print(path)
