"""Test token boundaries, stale diagnostics and last-message selection without hardware."""
import hashlib,json,os,subprocess,time
from pathlib import Path
R=Path(__file__).resolve().parent.parent;SOURCE=R/'linux-port/station-failure-parser.sh';out=R/'tools/test-artifacts'/('station-parser-'+str(time.time_ns()));out.mkdir()
token='1234567890abcdef1234567890abcdef';marker='LYNX_STATION_ATTEMPT_BEGIN '+token
messages=[('WMT turn on WIFI fail!',28),('Set p2p mode handler is NULL',29),('Get wlan0 net device timeout',30),('Set wlan mode fail',31),('Wi-Fi is resetting',32),('WIFI_write invalid param',33)]
spec=[('no-marker',116,'ordinary\n',35),('wrong-token',116,marker.replace(token,'f'*32)+'\nWMT turn on WIFI fail!\n',35),('token-suffix',116,marker+'extra\nWMT turn on WIFI fail!\n',35),('marker-prefix',116,'FAKE_'+marker+'\nWMT turn on WIFI fail!\n',35),('stale-error',116,'WMT turn on WIFI fail!\n'+marker+'\nordinary\n',34),('newest-attempt',116,marker+'\nWMT turn on WIFI fail!\n'+marker+'\nordinary\n',34),('last-message',116,marker+'\nWMT turn on WIFI fail!\nSet wlan mode fail\n',31),('open-failed',114,'',25),('type-failed',115,'',26),('arg-failed',117,'',27),('unknown-result',199,marker+'\nWMT turn on WIFI fail!\n',35)]
spec.extend(('message-'+str(code),116,marker+'\n'+message+'\n',code) for message,code in messages)
fake=out/'busybox';fake.write_text('#!/bin/sh\nexec "$@"\n');fake.chmod(0o755)
cases=[]
for name,status,log,expected in spec:
 f=out/name;f.mkdir();(f/'token').write_text(token+'\n');(f/'result').write_text(str(status)+'\n');(f/'dmesg').write_text(log)
 source=SOURCE.read_text().replace('/etc/lynx/session-token',str(f/'token')).replace('/run/lynx/station-result',str(f/'result')).replace('/run/lynx/station-dmesg',str(f/'dmesg'))
 script=f/'test.sh';script.write_text("BB='"+str(fake)+"'\n"+source+"\nlynx_station_failure_code\nprintf '%s\\n' \"$nt_station_code\"\n")
 p=subprocess.run(['sh',str(script)],capture_output=True,text=True,timeout=10)
 assert p.returncode==0 and p.stdout.strip()==str(expected),(name,p.stdout,p.stderr)
 cases.append({'case':name,'code':expected})
report={'passed':True,'source_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),'cases':cases,'phone_contacted':False}
path=out/'result.json';path.write_text(json.dumps(report,indent=2)+'\n');print(path)
