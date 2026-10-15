"""Check station request count, gated completion and first-failure preservation."""
import hashlib,json,subprocess,time
from pathlib import Path
R=Path(__file__).resolve().parent.parent;P=R/'linux-port';source=(P/'wifi-station-async.sh').read_text();out=R/'tools/test-artifacts'/('wifi-station-async-'+str(time.time_ns()));out.mkdir(mode=0o700);results=[]
for name,first,ready,second,count,success in [('initial-success',0,0,0,1,True),('not-ready',116,1,0,1,False),('completed',116,0,0,2,True),('second-fails',116,0,116,2,False)]:
    f=out/name;f.mkdir();run=f/'run';run.mkdir();(f/'token').write_text('f'*32+'\n');(f/'calls').write_text('0\n')
    bb=f/'busybox';bb.write_text('#!/bin/sh\n[ "$1" != dmesg ] || { echo captured; exit 0; }\nexec "$@"\n');bb.chmod(0o755)
    control=f/'control';control.write_text('#!/bin/sh\n[ "$1" = --station ] || exit 199\nread -r n < '+str(f/'calls')+'\nn=$((n+1)); printf "%s\\n" "$n" > '+str(f/'calls')+'\n[ "$n" -le 2 ] || exit 198\nif [ "$n" = 1 ]; then exit '+str(first)+'; else exit '+str(second)+'; fi\n');control.chmod(0o755)
    (f/'power-stack-parser.sh').write_text('lynx_power_failure_code() { nt_station_code=25; }\n')
    (f/'wifi-worker-stack.sh').write_text('lynx_capture_wifi_worker_stack() { echo stack > '+str(run/'wifi-worker-stack')+'; echo 0 > '+str(run/'wifi-worker-stack-result')+'; }\n')
    (f/'wifi-async-ready.sh').write_text('lynx_wifi_async_ready() { echo checked > '+str(f/'ready-called')+'; return '+str(ready)+'; }\n')
    body=source.replace('/etc/lynx/session-token',str(f/'token')).replace('/etc/lynx/',str(f)+'/').replace('/run/lynx',str(run)).replace('/dev/kmsg',str(f/'kmsg')).replace('/bin/lynx-wifi-control',str(control))
    script=f/'test.sh';script.write_text('BB='+str(bb)+'\nlog() { :; }\n'+body+'\nlynx_wifi_station_request\nexit $?\n')
    p=subprocess.run(['sh',str(script)],capture_output=True,text=True,timeout=10);assert (p.returncode==0)==success and int((f/'calls').read_text())==count,(name,p.stdout,p.stderr)
    if first==0:assert not (f/'ready-called').exists()
    else:assert (run/'station-result.first').read_text().strip()==str(first) and (run/'station-dmesg.first').read_text().strip()=='captured'
    results.append({'case':name,'passed':True,'station_calls':count})
path=out/'result.json';path.write_text(json.dumps({'passed':True,'source_sha256':hashlib.sha256(source.encode()).hexdigest(),'cases':results,'phone_contacted':False},indent=2)+'\n');print(path)
