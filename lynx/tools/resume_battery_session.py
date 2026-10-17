"""Resume verified RAM battery tooling after Lynx boots the existing V19 image.

No Fastboot operation, flash, reboot or unconditional shutdown. Start this
before a physical boot/reboot. Default prints instructions without contact.
"""
import argparse,hashlib,json,os,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
PORT=ROOT/'linux-port'
BASIS=PORT/'artifacts/gauge-module-basis-1792107325426159905'
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--start',action='store_true');parser.add_argument('--worker',type=Path);parser.add_argument('--runtime-power',action='store_true');parser.add_argument('--alpine-stage-receipt',type=Path);parser.add_argument('--usb-unplugged-confirmed',action='store_true');args=parser.parse_args();os.umask(0o077)
 if not args.start and args.worker is None:print('Use --start --usb-unplugged-confirmed [--runtime-power [--alpine-stage-receipt RECEIPT]] before booting existing V19. No image is flashed.');return
 if not args.usb_unplugged_confirmed:parser.error('Supervised battery resume requires current confirmation that Lynx is physically unplugged from USB')
 if args.alpine_stage_receipt:
  if not args.runtime_power:parser.error('--alpine-stage-receipt requires --runtime-power')
  args.alpine_stage_receipt=args.alpine_stage_receipt.resolve(strict=True)
  from configure_alpine_runtime import load_stage
  load_stage(args.alpine_stage_receipt) # Offline validation before starting a physical-boot listener.
 if args.worker is None:
  out=ROOT/'logs'/('battery-resume-'+str(time.time_ns()));out.mkdir(mode=0o700)
  with (out/'worker.stdout').open('wb') as stdout,(out/'worker.stderr').open('wb') as stderr:
   worker_args=[sys.executable,str(Path(__file__).resolve()),'--worker',str(out)]
   worker_args.append('--usb-unplugged-confirmed')
   if args.runtime_power:worker_args.append('--runtime-power')
   if args.alpine_stage_receipt:worker_args.extend(['--alpine-stage-receipt',str(args.alpine_stage_receipt)])
   child=subprocess.Popen(worker_args,cwd=ROOT,stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr,start_new_session=True)
  (out/'launcher.json').write_text(json.dumps({'pid':child.pid,'started_ns':time.time_ns(),'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},indent=2)+'\n')
  deadline=time.monotonic()+10
  while time.monotonic()<deadline:
   if (out/'result.json').exists():
    report=json.loads((out/'result.json').read_text())
    if report.get('listener_ready') or report['state']=='failed':print(json.dumps({'result':str(out/'result.json'),'pid':child.pid,**report},indent=2));return
   if child.poll() is not None:raise SystemExit('Resume worker exited; inspect '+str(out))
   time.sleep(.1)
  print(json.dumps({'result':str(out/'result.json'),'pid':child.pid,'state':'starting'}));return
 out=args.worker;report={'state':'starting','started_ns':time.time_ns(),'operations':[],'flash_performed':False,'unconditional_shutdown':False,'runtime_power_requested':args.runtime_power,'alpine_stage_receipt':str(args.alpine_stage_receipt) if args.alpine_stage_receipt else None}
 def save():
  p=out/'result.tmp';p.write_text(json.dumps(report,indent=2)+'\n');p.replace(out/'result.json')
 def run(name,argv,timeout=20):
  op={'name':name,'argv':argv,'started_ns':time.time_ns()};report['operations'].append(op);save()
  with (out/(name+'.stdout')).open('wb') as stdout,(out/(name+'.stderr')).open('wb') as stderr:
   p=subprocess.run(argv,cwd=ROOT,stdout=stdout,stderr=stderr,timeout=timeout)
  op.update(exit_code=p.returncode,finished_ns=time.time_ns());save()
  if p.returncode:raise ValueError(name+' failed; raw streams saved')
  return (out/(name+'.stdout')).read_text()
 def tool(name,*argv):return [sys.executable,str(ROOT/'tools'/name),*map(str,argv)]
 try:
  watch=(PORT/'battery-watch.sh').read_bytes();digest=hashlib.sha256(watch).hexdigest()
  tests=[json.loads(p.read_text()) for p in (PORT/'artifacts').glob('battery-watch-check-*/result.json')]
  if not any(r.get('passed') and r.get('source_sha256')==digest for r in tests):raise ValueError('Matching battery watcher tests missing')
  ready=json.loads(run('listener',tool('start_gauge_listener.py','--run-supervised-trial','--usb-unplugged-confirmed','--identity-query','--keep-running','--seconds','600')))
  if not ready['ready_verified']:raise ValueError('Listener not ready')
  session=Path(ready['trial_receipt']);report.update(state='waiting-native-ssh',listener_ready=True,session=str(session));save();deadline=time.monotonic()+620
  while time.monotonic()<deadline:
   trial=json.loads(session.read_text())
   if trial.get('finished_ns'):break
   time.sleep(.5)
  else:raise ValueError('Native-session discovery deadline')
  if not(trial.get('session_left_running') and trial.get('extra_diagnostic',{}).get('exit_code')==0):raise ValueError('Continuous identity session not established')
  report['state']='installing-battery-monitor';save()
  run('identity-analysis',tool('summarize_gauge_trial.py','--identity-query','--receipt',session))
  installed=json.loads(run('install-monitor',tool('install_battery_monitor.py','--basis',BASIS,'--session',session,'--install'),timeout=40))
  install_receipt=Path(installed['result']);raw=(install_receipt.parent/'load-and-snapshot.stdout').read_text();fields=dict(line.split('=',1) for line in raw.splitlines() if '=' in line)
  if any(fields.get(k)!='0' for k in ['temperature_error','voltage_error','current_error','capacity_error']):raise ValueError('Initial snapshot has field errors; leave SSH online for review')
  run('upload-battery-watch',tool('lynx_live_command.py','--session',session,'--name','upload-battery-watch','--command','test ! -e /run/lynx/battery-watch.sh && cat > /run/lynx/battery-watch.sh','--stdin-file',PORT/'battery-watch.sh'))
  command='set -e; test ! -e /run/lynx/battery-watch.pid; echo "'+digest+'  /run/lynx/battery-watch.sh" | /bin/busybox sha256sum -c -; /bin/busybox nohup /bin/busybox sh /run/lynx/battery-watch.sh > /run/lynx/battery-watch.log 2>&1 < /dev/null & pid=$!; echo "$pid" > /run/lynx/battery-watch.pid; /bin/busybox sleep 1; kill -0 "$pid"; cat /run/lynx/battery-last'
  run('start-battery-watch',tool('lynx_live_command.py','--session',session,'--name','start-battery-watch','--command',command))
  if args.runtime_power:
   report['state']='configuring-runtime-power';save()
   power=json.loads(run('runtime-power',tool('configure_runtime_power.py','--session',session,'--apply'),timeout=90))
   if power['state']!='ready':raise ValueError('Runtime power setup not ready; leave existing watchers online')
   report['runtime_power_receipt']=power['result'];save()
  logger=json.loads(run('host-logger',tool('collect_battery_session.py','--session',session,'--seconds','3600')))
  if logger['state']!='watching':raise ValueError('Host logger not ready')
  report['host_logger_receipt']=logger['result'];save()
  if args.alpine_stage_receipt:
   report['state']='configuring-alpine-runtime';save()
   clock=json.loads(run('alpine-clock',tool('sync_lynx_clock.py','--session',session,'--sync'),timeout=45))
   if not clock['passed']:raise ValueError('Wall-clock verification failed; retain native runtime')
   report['clock_analysis']=clock['analysis'];save()
   alpine=json.loads(run('alpine-runtime',tool('configure_alpine_runtime.py','--session',session,'--stage-receipt',args.alpine_stage_receipt,'--install'),timeout=240))
   if alpine['state']!='native-userspace-verified':raise ValueError('Alpine stage not ready; existing SSH, watchers and host logger remain online')
   report['alpine_runtime_receipt']=alpine['result'];save()
  report.update(state='online',monitor_install_receipt=str(install_receipt),host_logger_receipt=logger['result'],finished_ns=time.time_ns())
 except Exception as error:report.update(state='failed',error=str(error),finished_ns=time.time_ns())
 save()
if __name__=='__main__':main()
