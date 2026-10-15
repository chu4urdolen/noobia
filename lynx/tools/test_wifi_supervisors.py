"""Exercise both exact supervisor control flows with accelerated fixture clocks."""
import hashlib,json,os,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent;P=ROOT/'linux-port'
def main():
 out=ROOT/'tools/test-artifacts'/('wifi-supervisors-'+str(time.time_ns()));out.mkdir()
 fake=out/'busybox';fake.write_text('''#!/usr/bin/python3
import os,pathlib,shutil,sys,time
r=pathlib.Path(os.environ['FIXTURE']);args=sys.argv[1:]
if args[0]=='sleep':
 time.sleep(.005);p=r/'uptime';n=int(p.read_text().split('.')[0])+10;p.write_text(str(n)+'.00 0\\n')
elif args[0]=='cat':sys.stdout.buffer.write(pathlib.Path(args[1]).read_bytes())
elif args[0]=='mv':shutil.move(args[1],args[2])
else:sys.exit(2)
''');fake.chmod(0o755)
 nc=out/'nc';nc.write_text('#!/bin/sh\ncat >/dev/null\n');nc.chmod(0o755)
 reset=out/'reset';reset.write_text('''#!/usr/bin/python3
import os,pathlib
r=pathlib.Path(os.environ['FIXTURE'])
with (r/'resets').open('a') as f:f.write('reset\\n')
(r/'release').touch()
''');reset.chmod(0o755)
 cases=[];sources={}
 for which in ['bootstrap','wifi']:
  path=P/('lynx-wifi-bootstrap-runtime.sh' if which=='bootstrap' else 'lynx-wifi-runtime.sh');source=path.read_text();sources[which]=hashlib.sha256(path.read_bytes()).hexdigest()
  options=['success','failure','stalled','invalid-clock'] if which=='bootstrap' else ['success','failure','ready-no-host','wrong-token','stalled','invalid-clock']
  for case in options:
   folder=out/(which+'-'+case);(folder/'run/lynx').mkdir(parents=True);(folder/'etc/lynx').mkdir(parents=True);(folder/'run/lynx/boot.log').touch()
   (folder/'uptime').write_text('invalid 0\n' if case=='invalid-clock' else '0.00 0\n');(folder/'etc/lynx/host-ip').write_text('127.0.0.1\n');(folder/'etc/lynx/session-token').write_text('fixture-token\n')
   code=source.replace('/run/lynx',str(folder/'run/lynx')).replace('/etc/lynx',str(folder/'etc/lynx')).replace('/proc/uptime',str(folder/'uptime')).replace('/bin/boot-proof-reboot',str(reset)).replace('/usr/bin/nc',str(nc))
   name='lynx_wifi_bootstrap_child' if which=='bootstrap' else 'lynx_wifi_worker'
   result='return 151' if which=='bootstrap' else 'return 134'
   if case=='success':
    result='return 0' if which=='bootstrap' else f"printf '%s\\n' fixture-token > '{folder}/run/lynx/host-confirmed'; return 0"
   elif case in ['ready-no-host','wrong-token']:
    result=f"printf ready > '{folder}/run/lynx/ssh-ready'; "
    if case=='wrong-token':result+=f"printf wrong > '{folder}/run/lynx/host-confirmed'; "
    result+='return 0'
   elif case=='stalled':result=f"while [ ! -f '{folder}/release' ]; do sleep .01; done; return 149"
   invoke='lynx_wifi_bootstrap' if which=='bootstrap' else 'lynx_wifi_supervise'
   script=folder/'test.sh';script.write_text(f"BB='{fake}'\nlog() {{ printf '%s\\n' \"$*\"; }}\n"+code+f'\n{name}() {{ {result}; }}\n{invoke}\n')
   started=time.monotonic();process=subprocess.run(['sh',str(script)],env=dict(os.environ,FIXTURE=str(folder)),capture_output=True,text=True,timeout=30)
   (folder/'stdout').write_text(process.stdout);(folder/'stderr').write_text(process.stderr)
   resets=(folder/'resets').read_text().splitlines() if (folder/'resets').exists() else []
   expected=0 if case=='success' else 1;assert process.returncode==expected,(which,case,process.stderr)
   assert len(resets)==(0 if case in ['success','invalid-clock'] else 1),(which,case,resets)
   if case in ['stalled','ready-no-host','wrong-token']:assert int((folder/'uptime').read_text().split('.')[0])==(180 if which=='bootstrap' else 240),(which,case)
   cases.append({'which':which,'case':case,'exit_code':process.returncode,'reset_calls':len(resets),'seconds':time.monotonic()-started})
 receipt=out/'result.json';receipt.write_text(json.dumps({'passed':True,'source_sha256':sources,'cases':cases,'phone_contacted':False,'real_reboots':False,'limits':'Host shell fixtures verify control flow only; no MT6983 probe scheduling or actual kernel shutdown is emulated.'},indent=2)+'\n');print(receipt)
if __name__=='__main__':main()
