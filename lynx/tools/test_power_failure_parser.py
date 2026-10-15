"""Exercise marked-attempt isolation, numeric boundaries and failure commit order."""
import hashlib,json,subprocess,time
from pathlib import Path
R=Path(__file__).resolve().parent.parent;SOURCE=R/'linux-port/power-failure-parser.sh'
out=R/'tools/test-artifacts'/('power-parser-'+str(time.time_ns()));out.mkdir()
token='1234567890abcdef1234567890abcdef';marker='LYNX_STATION_ATTEMPT_BEGIN '+token
fail='WMT turn on WIFI fail!\n'
spec=[('missing-marker',116,fail,35),('wrong-token',116,marker.replace(token,'f'*32)+'\nwlanProbe: probe failed, reason:3\n'+fail,35),('suffix-marker',116,marker+'x\nwlanProbe: probe failed, reason:3\n'+fail,35),('prefix-marker',116,'FAKE_'+marker+'\nwlanProbe: probe failed, reason:3\n'+fail,35),('stale',116,'wlanProbe: probe failed, reason:3\n'+marker+'\n'+fail,35),('latest-attempt',116,marker+'\nwlanProbe: probe failed, reason:3\n'+marker+'\n'+fail,35),('no-power-failure',116,marker+'\nwlanProbe: probe failed, reason:3\n',35),('late-detail',116,marker+'\n'+fail+'wlanProbe: probe failed, reason:3\n',35),('numeric-suffix',116,marker+'\nwlanProbe: probe failed, reason:30\n'+fail,35),('negative',116,marker+'\nwlanProbe: probe failed, reason:-1\n'+fail,35),('unknown-reason',116,marker+'\nwlanProbe: probe failed, reason:8\n'+fail,35),('wrong-component-pointer',116,marker+'\nOther Invalid pointer\n'+fail,35),('timeout',116,marker+'\n[WIFI-FW] WiFi on/off takes more than 30 seconds\n'+fail,25),('pointer',116,marker+'\n[WIFI-FW] func[E]: Invalid pointer\n'+fail,26),('last-detail',116,marker+'\nwlanProbe: probe failed, reason:3\n[WIFI-FW] WiFi on/off takes more than 30 seconds\n'+fail,25),('last-committed',116,marker+'\nwlanProbe: probe failed, reason:3\n'+fail+'wlanProbe: probe failed, reason:2\n'+fail,29),('status-other',114,marker+'\nwlanProbe: probe failed, reason:3\n'+fail,35)]
spec.extend(('reason-'+str(n),116,marker+'\n[k] wlanProbe: probe failed, reason:'+str(n)+'  \n'+fail,27+n) for n in range(8))
fake=out/'busybox';fake.write_text('#!/bin/sh\nexec "$@"\n');fake.chmod(0o755);cases=[]
for name,status,log,expected in spec:
    f=out/name;f.mkdir();(f/'token').write_text(token+'\n');(f/'result').write_text(str(status)+'\n');(f/'dmesg').write_text(log)
    source=SOURCE.read_text().replace('/etc/lynx/session-token',str(f/'token')).replace('/run/lynx/station-result',str(f/'result')).replace('/run/lynx/station-dmesg',str(f/'dmesg'))
    script=f/'test.sh';script.write_text('BB='+str(fake)+'\n'+source+'\nlynx_station_failure_code\nprintf "%s\\n" "$nt_station_code"\n')
    p=subprocess.run(['sh',str(script)],capture_output=True,text=True,timeout=10)
    assert p.returncode==0 and p.stdout.strip()==str(expected),(name,p.stdout,p.stderr)
    cases.append({'case':name,'code':expected})
path=out/'result.json';path.write_text(json.dumps({'passed':True,'source_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),'cases':cases,'phone_contacted':False},indent=2)+'\n');print(path)
