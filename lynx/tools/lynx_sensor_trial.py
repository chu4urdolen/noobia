"""Bounded discovery, pinned SSH, sensor-only RAM trial, then power-off request.

No flash, reboot, charging changes or CPU-frequency module loading. Start the
listener before the human powers on the cooled handset. Physical shutdown is
still required if the kernel hangs or power-off does not work.
"""
import argparse,hashlib,io,json,os,re,socket,subprocess,tarfile,time
from pathlib import Path
from lynx_wifi_v19_contact import BUILD,ssh_command,PROOF,proof_valid,beacon_valid
R=Path(__file__).resolve().parent.parent;P=R/'linux-port'
PACK=P/'artifacts/thermal-ssh-pack-1792099635423460996'
EXPECTED='edc011a45072b6c3baa13da4ba73462d7a0e049236719a54fb093fb2da0ebffb'
TRIAL_SCOPE=['soc-temperature']
REMOTE='/run/lynx/thermal-sensor-trial'
TRIAL_PREFIX=None
POST_CPU_HOOK=None
EXTRA_DIAGNOSTIC=None
def sha(data):return hashlib.sha256(data).hexdigest()
def arm_command(token):
 assert re.fullmatch('[0-9a-f]{32}',token)
 return r'''/bin/busybox nohup /bin/busybox sh /run/lynx/thermal-stop.sh > /run/lynx/thermal-stop.log 2>&1 < /dev/null &
pid=$!
printf '%s\n' "$pid" > /run/lynx/thermal-stop.pid
/bin/busybox sleep 1
kill -0 "$pid" || exit 1
printf '%s\n' 'BOOT_TOKEN' > /run/lynx/host-confirmed.tmp && /bin/busybox mv /run/lynx/host-confirmed.tmp /run/lynx/host-confirmed || exit 1
printf 'STOP_TIMER_ARMED\n'
'''.replace('BOOT_TOKEN',token)
def validate():
 data=(PACK/'thermal-ssh-pack.tar.gz').read_bytes();assert sha(data)==EXPECTED
 manifest=json.loads((PACK/'manifest.json').read_text());assert manifest['live_trial_eligible'] and manifest['trial_scope']==TRIAL_SCOPE and manifest['groups']['cpu-frequency']['review_only']==('cpu-frequency' not in TRIAL_SCOPE)
 with tarfile.open(fileobj=io.BytesIO(data),mode='r:gz') as t:
  members=t.getmembers();assert all(m.isfile() and not m.name.startswith('/') and '..' not in Path(m.name).parts for m in members)
  files={m.name:t.extractfile(m).read() for m in members};assert len(files)==len(members)
  assert 'REVIEW-HOLD' not in files and files['ALLOWED-STAGES']==''.join(n+'\n' for n in TRIAL_SCOPE).encode()
  for line in files['SHA256SUMS'].decode().splitlines():
   digest,name=line.split('  ',1);assert sha(files[name])==digest
 checks=[(f,json.loads(f.read_text())) for f in sorted((P/'artifacts').glob('emulated-thermal-pack-guards-*/result.json'))];matching=[r for f,r in checks if r.get('passed') and r.get('archive_sha256')==EXPECTED];assert matching;check=matching[-1];assert check['runtime_sha256']==sha(files['thermal-step.sh'])
 if 'cpu-frequency' in TRIAL_SCOPE:assert check['cpu_guard_sha256']==sha(files['cpu-temperature-guard.sh']) and all(v for k,v in check['checks'].items() if k.startswith('cpu_'))
 timers=sorted((P/'artifacts').glob('emulated-thermal-stop-*/result.json'));timer=json.loads(timers[-1].read_text());assert timer['passed'] and timer['source_sha256']==sha((P/'thermal-stop.sh').read_bytes())
 assert (P/'docs/SAFETY-HOLD.json').exists() # Do not clear the flash hold.
 return data
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--listen',action='store_true');parser.add_argument('--self-test',action='store_true');parser.add_argument('--seconds',type=int,default=300);args=parser.parse_args();data=validate()
 if args.self_test:
  assert beacon_valid(('LYNX_HELLO '+BUILD['session_token']).encode(),'192.168.100.9') and not beacon_valid(b'bad','192.168.100.9')
  arm=arm_command(BUILD['session_token']);assert "printf '%s\\n'" in arm
  p=subprocess.run(['sh','-c',"printf '%s\\n' probe"],capture_output=True);assert p.stdout==b'probe\n'
  print('Checked '+', '.join(TRIAL_SCOPE)+' pack/guards/identity/timer acknowledgement policy; no phone contacted.');return
 if not args.listen:print('Use --listen only for a cooled, supervised handset boot.');return
 assert 30<=args.seconds<=600;os.umask(0o077)
 out=R/'logs'/((TRIAL_PREFIX or ('cpu-trial-' if 'cpu-frequency' in TRIAL_SCOPE else 'sensor-trial-'))+str(time.time_ns()));out.mkdir(mode=0o700);receipt=out/'result.json'
 report={'state':'starting','started_ns':time.time_ns(),'phone_contacted':False,'native_identity_verified':False,'flash_performed':False,'cpu_frequency_modules_allowed':'cpu-frequency' in TRIAL_SCOPE,'trial_scope':TRIAL_SCOPE,'pack_sha256':EXPECTED,'operations':[]}
 if EXTRA_DIAGNOSTIC is not None:report['extra_diagnostic_preflight']=EXTRA_DIAGNOSTIC
 def save():
  temp=receipt.with_suffix('.tmp');temp.write_text(json.dumps(report,indent=2)+'\n');temp.replace(receipt)
 def run(ip,name,command,timeout=8,stdin=None):
  op={'name':name,'started_ns':time.time_ns(),'started_monotonic':time.monotonic(),'remote_command':command};report['operations'].append(op);save();print('SENSOR_TRIAL_PHASE:',name,flush=True)
  stdout_path=out/(name+'.stdout');stderr_path=out/(name+'.stderr');rc=None
  with stdout_path.open('wb') as stdout,stderr_path.open('wb') as stderr:
   try:rc=subprocess.run(ssh_command(ip,command),input=stdin,stdout=stdout,stderr=stderr,timeout=timeout).returncode
   except subprocess.TimeoutExpired:op['timed_out']=True
  raw=stdout_path.read_bytes();op.update(exit_code=rc,finished_ns=time.time_ns(),elapsed_seconds=time.monotonic()-op['started_monotonic'],stdout_bytes=len(raw),stdout_sha256=sha(raw));save();return raw,rc
 save()
 with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as listener:
  listener.bind((BUILD['collector_ip'],5514));listener.settimeout(.5);report.update(state='listening',ready_ns=time.time_ns());save();print('SENSOR LISTENER READY:',receipt,flush=True)
  deadline=time.monotonic()+args.seconds
  while time.monotonic()<deadline:
   report['heartbeat_ns']=time.time_ns();save()
   try:beacon,address=listener.recvfrom(4096)
   except socket.timeout:continue
   if not beacon_valid(beacon,address[0]):continue
   ip=address[0];report.update(phone_contacted=True,phone_ip=ip,beacon_received_ns=time.time_ns());save()
   proof,rc=run(ip,'identity',PROOF)
   if not proof_valid(proof.decode(errors='replace'),rc):report['state']='identity-failed';save();return
   report.update(native_identity_verified=True,state='identity-verified');save()
   try:
    _,rc=run(ip,'upload-stop','cat > /run/lynx/thermal-stop.sh',stdin=(P/'thermal-stop.sh').read_bytes());assert rc==0,'Stop script transfer failed'
    # Arm the independent timer BEFORE acknowledging/cancelling normal fallback.
    token=BUILD['session_token']
    arm=arm_command(token)
    raw,rc=run(ip,'arm-stop-and-confirm',arm);assert rc==0 and b'STOP_TIMER_ARMED' in raw,'Stop timer not armed';report['stop_timer_armed']=True;save()
    _,rc=run(ip,'upload-pack','test ! -e '+REMOTE+' && mkdir -m 700 '+REMOTE+' && tar -xz -C '+REMOTE,timeout=12,stdin=data);assert rc==0,'Pack transfer failed'
    _,rc=run(ip,'before',"cat /proc/uptime /proc/mounts; /bin/busybox sh "+REMOTE+"/thermal-step.sh --inspect",timeout=8);assert rc==0,'Snapshot failed'
    raw,rc=run(ip,'sensor-stage','/bin/busybox sh '+REMOTE+'/thermal-step.sh --load soc-temperature',timeout=15);report['sensor_stage_exit_code']=rc;save()
    if rc==0 and 'cpu-frequency' in TRIAL_SCOPE:
     raw,rc=run(ip,'cpu-frequency-stage','/bin/busybox sh '+REMOTE+'/thermal-step.sh --load cpu-frequency',timeout=15);report['cpu_frequency_stage_exit_code']=rc;save()
     if rc==0 and POST_CPU_HOOK is not None:
      report['extra_diagnostic']=POST_CPU_HOOK(run,ip);save()
    _,diagrc=run(ip,'kernel-and-sensors',"dmesg; printf '\\nTHERMAL_FINAL\\n'; /bin/busybox sh "+REMOTE+"/thermal-step.sh --inspect; printf '\\nBINDINGS\\n'; ls -l /sys/bus/platform/devices/10315000.lvts/driver /sys/bus/platform/devices/11ee0000.efuse/driver; true",timeout=8)
    report.update(state='sensor-stage-returned' if rc==0 else 'sensor-stage-failed-or-hung',diagnostics_exit_code=diagrc)
    if 'cpu-frequency' in TRIAL_SCOPE:
     _,sample_rc=run(ip,'cpu-and-battery-observation',"/bin/busybox sleep 1; /bin/busybox sh "+REMOTE+"/thermal-step.sh --inspect; printf '\\nI2C_CLIENTS\\n'; for p in /sys/bus/i2c/devices/*; do [ -r \"$p/name\" ] || continue; echo \"$p\"; cat \"$p/name\"; readlink \"$p/driver\"; done; printf '\\nOMRG_RULES\\n'; for f in /sys/bus/platform/devices/*/oplus-omrg*/ruler_enable; do [ -r \"$f\" ] || continue; echo \"$f\"; cat \"$f\"; done; true",timeout=8)
     report.update(state='cpu-stage-returned' if rc==0 else 'cpu-stage-failed-or-hung',second_sample_exit_code=sample_rc)
    if 'extra_diagnostic' in report:
     report['state']='gauge-stage-returned' if report['extra_diagnostic']['exit_code']==0 else 'gauge-stage-failed-or-hung'
   except Exception as error:report.update(state='trial-error',error=str(error))
   finally:
    # Always request stop; the independent timer is never cancelled.
    raw,rc=run(ip,'request-poweroff','/bin/busybox poweroff -f',timeout=5);report.update(poweroff_request_exit_code=rc,physical_poweroff_confirmed=False,finished_ns=time.time_ns());save()
   print('SENSOR TRIAL FINISHED:',receipt,flush=True);print('Confirm physical power-off; no further driver stages will run.',flush=True);return
 report.update(state='discovery-deadline',finished_ns=time.time_ns());save();print('No verified contact; receipt:',receipt,flush=True)
if __name__=='__main__':main()
