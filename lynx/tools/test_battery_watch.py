"""Run battery-watcher source against fixtures; power-off is mocked."""
import hashlib,json,os,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
def main():
 raw=(ROOT/'linux-port/battery-watch.sh').read_bytes();out=ROOT/'linux-port/artifacts'/('battery-watch-check-'+str(time.time_ns()));out.mkdir(mode=0o700)
 specs=[('normal','20600',0,False),('below-cutoff','44999',0,False),('at-cutoff','45000',0,True),('above-cutoff','50000',0,True),('freezing','0',0,False),('negative','-1000',0,False),('read-error','0',-5,False),('invalid','bad',0,False),('missing',None,0,False)];rows=[]
 for name,temp,error,stop in specs:
  f=out/name;f.mkdir();source=f/'snapshot';last=f/'last';shim=f/'busybox-fixture'
  if temp is not None:source.write_text('temperature_millidegrees_celsius='+temp+'\ntemperature_error='+str(error)+'\n')
  shim.write_text('#!/bin/sh\n[ "$1" = poweroff ] && { echo stop >> "$BATTERY_STOP_LOG"; exit 0; }\nexec /usr/bin/"$@"\n');shim.chmod(0o700)
  text=raw.decode().replace('BB=/bin/busybox','BB='+str(shim)).replace('SOURCE=/sys/bus/i2c/devices/7-0055/battery_snapshot','SOURCE='+str(source)).replace('LAST=/run/lynx/battery-last','LAST='+str(last));(f/'script.sh').write_text(text)
  p=subprocess.run(['sh',str(f/'script.sh'),'--once'],capture_output=True,timeout=3,env=dict(os.environ,BATTERY_STOP_LOG=str(f/'stop.log')));(f/'stdout').write_bytes(p.stdout);(f/'stderr').write_bytes(p.stderr)
  expected=2 if stop else 1 if name in ['read-error','invalid','missing'] else 0
  rows.append({'case':name,'passed':(f/'stop.log').exists()==stop and p.returncode==expected and last.exists(),'exit_code':p.returncode})
 result={'passed':all(r['passed'] for r in rows),'source_sha256':hashlib.sha256(raw).hexdigest(),'cases':rows,'phone_contacted':False,'actual_poweroff_performed':False};(out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'result':str(out/'result.json'),**result},indent=2))
 if not result['passed']:raise SystemExit(1)
if __name__=='__main__':main()
