"""Validate and install the read-only monitor in a verified live ZY0603 session.

Only RAM upload/module load and one snapshot. No flash or implicit shutdown.
"""
import argparse,hashlib,json,os,subprocess,time
from pathlib import Path
from lynx_wifi_v19_contact import PROOF,proof_valid,ssh_command
ROOT=Path(__file__).resolve().parent.parent;PORT=ROOT/'linux-port'
def sha(data):return hashlib.sha256(data).hexdigest()
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--basis',type=Path,required=True);parser.add_argument('--session',type=Path,required=True);parser.add_argument('--install',action='store_true');args=parser.parse_args()
 session=json.loads(args.session.read_text());identity=json.loads((args.session.parent/'analysis.json').read_text());build=json.loads((args.basis/'build-result.json').read_text())
 if not(session.get('session_left_running') and session.get('native_identity_verified') and identity.get('identity_query_verified') and identity.get('raw_register_word')==42495):raise ValueError('Requires verified live ZY0603 identity')
 data=(args.basis/'module/lynx-battery-monitor.ko').read_bytes();digest=sha(data)
 if not(build['passed'] and build['module_sha256']==digest and build.get('module_name')=='lynx-battery-monitor' and build['source_sha256']==sha((PORT/'lynx-battery-monitor.c').read_bytes())):raise ValueError('Monitor build/source identity differs')
 vms=[json.loads(p.read_text()) for p in (PORT/'artifacts').glob('emulated-gauge-sample-*/result.json')]
 if not any(r.get('passed') and r.get('module_sha256')==digest for r in vms):raise ValueError('Matching stock-kernel VM test missing')
 tests=[json.loads(p.read_text()) for p in (PORT/'artifacts').glob('battery-monitor-logic-*/result.json')]
 if not any(r.get('passed') and r.get('source_sha256')==build['source_sha256'] for r in tests):raise ValueError('Matching C logic test missing')
 if not args.install:print('Monitor identity, source, stock-kernel VM and C logic verified; no phone contacted.');return
 os.umask(0o077);out=ROOT/'logs'/('battery-monitor-install-'+str(time.time_ns()));out.mkdir(mode=0o700)
 report={'started_ns':time.time_ns(),'module_sha256':digest,'session':str(args.session.resolve()),'phone_ip':session['phone_ip'],'flash_performed':False,'implicit_shutdown':False,'operations':[]}
 def run(name,command,payload=None,timeout=10):
  op={'name':name,'command':command,'started_ns':time.time_ns()};report['operations'].append(op)
  with (out/(name+'.stdout')).open('wb') as stdout,(out/(name+'.stderr')).open('wb') as stderr:
   try:op['exit_code']=subprocess.run(ssh_command(session['phone_ip'],command),input=payload,stdout=stdout,stderr=stderr,timeout=timeout).returncode
   except subprocess.TimeoutExpired:op.update(exit_code=None,timed_out=True)
  raw=(out/(name+'.stdout')).read_bytes();op.update(finished_ns=time.time_ns(),stdout_sha256=sha(raw),stdout_bytes=len(raw));(out/'result.json').write_text(json.dumps(report,indent=2)+'\n');return raw,op['exit_code']
 try:
  raw,rc=run('identity',PROOF)
  if not proof_valid(raw.decode(errors='replace'),rc):raise ValueError('Live native identity failed')
  report['native_identity_verified']=True
  _,rc=run('upload','test ! -e /run/lynx/battery-monitor.ko && cat > /run/lynx/battery-monitor.ko',data)
  if rc!=0:raise ValueError('Module upload failed')
  command=r'''set -e
BB=/bin/busybox
[ -e /run/lynx/gauge-sample.started ]
[ ! -e /run/lynx/battery-monitor.started ]
[ ! -e /sys/module/lynx_battery_monitor ]
[ ! -e /sys/bus/i2c/devices/7-0055/driver ] && [ ! -L /sys/bus/i2c/devices/7-0055/driver ]
kill -0 "$($BB cat /run/lynx/thermal-watch.pid)"
echo 'MODULE_HASH  /run/lynx/battery-monitor.ko' | $BB sha256sum -c -
. /run/lynx/thermal-cpu-trial/cpu-temperature-guard.sh
lynx_cpu_temperature_guard
echo started > /run/lynx/battery-monitor.started
$BB insmod /run/lynx/battery-monitor.ko allow_reads=1 confirmed_device_type=42495
echo BATTERY_MONITOR_LOADED=1
$BB cat /sys/bus/i2c/devices/7-0055/battery_snapshot
'''.replace('MODULE_HASH',digest)
  raw,rc=run('load-and-snapshot',command)
  report.update(load_command_exit_code=rc,monitor_loaded_marker=b'BATTERY_MONITOR_LOADED=1' in raw)
  run('kernel-and-watch','dmesg; tail -n 5 /run/lynx/thermal-watch.log')
 except Exception as error:report['error']=str(error)
 report['finished_ns']=time.time_ns();(out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'result':str(out/'result.json'),'monitor_loaded':report.get('monitor_loaded_marker',False),'exit_code':report.get('load_command_exit_code'),'error':report.get('error')},indent=2))
 if report.get('load_command_exit_code')!=0:raise SystemExit(1)
if __name__=='__main__':main()
