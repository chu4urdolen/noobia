"""Bounded detached host logger; reads cached battery/thermal observations.

Stopping this logger never shuts down or reboots Lynx. Raw SSH captures and
host timestamps are preserved for every sample, including failures.
"""
import argparse,hashlib,json,os,subprocess,sys,time
from pathlib import Path
from lynx_wifi_v19_contact import PROOF,proof_valid,ssh_command
ROOT=Path(__file__).resolve().parent.parent
COMMAND="printf 'UPTIME\\n'; cat /proc/uptime; printf 'CPU_WATCH\\n'; tail -n 2 /run/lynx/thermal-watch.log; printf 'BATTERY_SNAPSHOT\\n'; cat /run/lynx/battery-last || echo BATTERY_SNAPSHOT_UNAVAILABLE; printf 'BATTERY_WATCH\\n'; tail -n 2 /run/lynx/battery-watch.log; printf 'SOFT_THROTTLE_WATCH\\n'; tail -n 4 /run/lynx/thermal-cooling-watch.log 2>/dev/null || echo SOFT_THROTTLE_NOT_INSTALLED; printf 'HEALTH_SUPERVISOR\\n'; tail -n 4 /run/lynx/health-supervisor/events.log 2>/dev/null || echo HEALTH_SUPERVISOR_NOT_INSTALLED; true"
def verified_running_session(session):
 continuous=(session.get('native_identity_verified') and session.get('session_left_running'))
 fresh_contact=(session.get('native_ssh_verified') and session.get('state')=='native-ssh-available' and session.get('fallback_cancel_ack_exit_code')==0)
 return bool(continuous or fresh_contact)
def main():
 p=argparse.ArgumentParser();p.add_argument('--session',type=Path,required=True);p.add_argument('--seconds',type=int,default=3600);p.add_argument('--run',type=Path);a=p.parse_args()
 if not 10<=a.seconds<=14400:raise ValueError('Bounded logging duration must be 10–14400 seconds')
 os.umask(0o077)
 if a.run is None:
  out=ROOT/'logs'/('battery-session-'+str(time.time_ns()));out.mkdir(mode=0o700)
  with (out/'worker.stdout').open('wb') as stdout,(out/'worker.stderr').open('wb') as stderr:
   child=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--session',str(a.session.resolve()),'--seconds',str(a.seconds),'--run',str(out)],stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr,start_new_session=True,cwd=ROOT)
  (out/'launcher.json').write_text(json.dumps({'pid':child.pid,'started_ns':time.time_ns(),'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},indent=2)+'\n')
  deadline=time.monotonic()+8
  while time.monotonic()<deadline:
   if (out/'result.json').exists():
    r=json.loads((out/'result.json').read_text())
    if r['state'] in ['watching','identity-failed','finished']:print(json.dumps({'result':str(out/'result.json'),'pid':child.pid,'state':r['state']}));return
   if child.poll() is not None:raise SystemExit('Logger exited before readiness; inspect '+str(out))
   time.sleep(.1)
  print(json.dumps({'result':str(out/'result.json'),'pid':child.pid,'state':'starting'}));return
 out=a.run;session=json.loads(a.session.read_text())
 if not verified_running_session(session):raise ValueError('Verified running V19 session required')
 report={'state':'starting','phone_ip':session['phone_ip'],'started_ns':time.time_ns(),'samples':0,'seconds':a.seconds,'implicit_shutdown':False}
 def save():
  t=out/'result.tmp';t.write_text(json.dumps(report,indent=2)+'\n');t.replace(out/'result.json')
 def run(name,command):
  started=time.time_ns()
  with (out/(name+'.stdout')).open('wb') as stdout,(out/(name+'.stderr')).open('wb') as stderr:
   try:rc=subprocess.run(ssh_command(session['phone_ip'],command),stdout=stdout,stderr=stderr,timeout=6).returncode
   except subprocess.TimeoutExpired:rc=None
  raw=(out/(name+'.stdout')).read_bytes()
  return raw,{'started_ns':started,'finished_ns':time.time_ns(),'exit_code':rc,'stdout_bytes':len(raw),'stdout_sha256':hashlib.sha256(raw).hexdigest(),'name':name}
 raw,op=run('identity',PROOF);report['native_identity_verified']=proof_valid(raw.decode(errors='replace'),op['exit_code']);report['identity']=op
 if not report['native_identity_verified']:report['state']='identity-failed';save();return
 report['state']='watching';save();deadline=time.monotonic()+a.seconds
 with (out/'samples.jsonl').open('a') as journal:
  while time.monotonic()<deadline:
   raw,entry=run('sample-'+str(report['samples']).zfill(5),COMMAND);journal.write(json.dumps(entry)+'\n');journal.flush();report.update(samples=report['samples']+1,last_sample_ns=entry['finished_ns'],last_exit_code=entry['exit_code']);save();time.sleep(min(10,max(0,deadline-time.monotonic())))
 report.update(state='finished',finished_ns=time.time_ns());save()
if __name__=='__main__':main()
