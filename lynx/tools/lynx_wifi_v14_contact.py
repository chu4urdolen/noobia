"""Receive Lynx public beacons; prove identity by pinned SSH; save private diagnostics."""
import argparse,hashlib,ipaddress,json,re,socket,subprocess,time
from pathlib import Path
from lynx_decode_stages import decode
ROOT=Path(__file__).resolve().parent.parent
F=ROOT/'linux-port/artifacts/busybox-wifi-ssh-twostage-v14'
BUILD=json.loads((F/'build-validation.json').read_text())
KERNEL='5.10.149-android12-9-o-g311738fbb5a8'
BB_SHA='999cb969d09093a71716cfc747bb53cdada3f332c05eb5046c56e0f66a4d6d22'
def ssh_command(ip,command):
 return ['ssh','-o','BatchMode=yes','-o','IdentitiesOnly=yes','-o','StrictHostKeyChecking=yes','-o','GlobalKnownHostsFile=/dev/null','-o','HostKeyAlias=lynx','-o','UserKnownHostsFile='+str(ROOT/'secrets/lynx_known_hosts'),'-o','ConnectTimeout=5','-i',str(ROOT/'secrets/nexus_lynx_ed25519'),'root@'+ip,command]
def beacon_valid(data,ip):
 try:network_ok=ipaddress.ip_address(ip) in ipaddress.ip_network('192.168.100.0/24')
 except ValueError:return False
 return network_ok and data.strip()==('LYNX_HELLO '+BUILD['session_token']).encode()
def proof_valid(text,exit_code):
 return exit_code==0 and 'LYNX_NATIVE_SSH_PROOF\n' in text and KERNEL+'\n' in text and '/bin/busybox\n' in text and BUILD['init_sha256']+'  /init' in text and BB_SHA+'  /bin/busybox' in text and BUILD['session_token']+'\n' in text and 'uid=0(root)' in text
PROOF="printf 'LYNX_NATIVE_SSH_PROOF\\n'; uname -r; readlink /proc/1/exe; sha256sum /init /bin/busybox; cat /etc/lynx/session-token; id"
DIAGNOSTICS="printf 'BOOT_LOG\\n'; cat /run/lynx/boot.log; printf 'KERNEL_LOG\\n'; dmesg; printf 'NETWORK_STATE\\n'; ip addr; ip route; for n in wlan0 wlan1; do [ -d /sys/class/net/$n ] && /sbin/wpa_cli -p /run/wpa_supplicant -i $n status; done; printf 'PSTORE_RECORDS\\n'; ls -l /sys/fs/pstore; for f in /sys/fs/pstore/*; do [ -f \"$f\" ] && { printf '\\nPSTORE %s\\n' \"$f\"; cat \"$f\"; }; done; printf 'MOUNTS\\n'; cat /proc/mounts; printf 'DRIVER_LOGS\\n'; cat /run/lynx/wpa.log /run/lynx/dropbear.log; true"
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--listen',action='store_true');parser.add_argument('--self-test',action='store_true');parser.add_argument('--seconds',type=int,default=600);args=parser.parse_args()
 if args.self_test:
  text='LYNX_NATIVE_SSH_PROOF\n'+KERNEL+'\n/bin/busybox\n'+BUILD['init_sha256']+'  /init\n'+BB_SHA+'  /bin/busybox\n'+BUILD['session_token']+'\nuid=0(root)\n'
  assert proof_valid(text,0) and not proof_valid(text,1) and not proof_valid(text.replace(KERNEL,'wrong-kernel'),0) and not proof_valid(text.replace(BUILD['init_sha256'],'wrong-init'),0)
  assert beacon_valid(('LYNX_HELLO '+BUILD['session_token']).encode(),'192.168.100.42')
  assert not beacon_valid(b'LYNX_HELLO wrong','192.168.100.42') and not beacon_valid(('LYNX_HELLO '+BUILD['session_token']).encode(),'192.168.8.42')
  print('Beacon and pinned-identity proof checks passed; no phone contacted.');return
 if not args.listen:print('Use --listen to start the bounded Noobia listener.');return
 assert 1<=args.seconds<=900 and re.fullmatch('[0-9a-f]{32}',BUILD['session_token'])
 out=ROOT/'logs'/('wifi-v14-contact-'+str(time.time_ns()));out.mkdir(mode=0o700)
 receipt=out/'result.json';report={'state':'starting','session_token':BUILD['session_token'],'bind_ip':BUILD['collector_ip'],'port':5514,'native_ssh_verified':False,'events':[],'started_ns':time.time_ns(),'started_monotonic':time.monotonic(),'collector_tool_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
 def save():
  tmp=receipt.with_suffix('.tmp');tmp.write_text(json.dumps(report,indent=2)+'\n');tmp.replace(receipt)
 save();started=time.monotonic();last_attempt={}
 with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as s:
  s.bind((BUILD['collector_ip'],5514));s.settimeout(.5);report['state']='listening';save();print('LISTENER READY:',receipt,flush=True)
  while time.monotonic()-started<args.seconds:
   report['heartbeat_ns']=time.time_ns();report['heartbeat_monotonic']=time.monotonic();report['elapsed_seconds']=report['heartbeat_monotonic']-started;save()
   try:data,address=s.recvfrom(4096)
   except socket.timeout:continue
   ip=address[0];event={'received_ns':time.time_ns(),'received_monotonic':time.monotonic(),'source_ip':ip,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'valid_beacon':beacon_valid(data,ip)};report['events'].append(event);save()
   (out/('datagram-'+str(len(report['events']))+'.bin')).write_bytes(data)
   if not event['valid_beacon'] or time.monotonic()-last_attempt.get(ip,-100)<5:continue
   last_attempt[ip]=time.monotonic();command=ssh_command(ip,PROOF);event['ssh_command']=command;event['ssh_started_ns']=time.time_ns();save()
   try:p=subprocess.run(command,capture_output=True,timeout=15)
   except subprocess.TimeoutExpired as e:
    (out/'ssh-timeout.raw').write_bytes((e.stdout or b'')+(e.stderr or b''));event['ssh_state']='timeout';save();continue
   raw=p.stdout+p.stderr;(out/('ssh-attempt-'+str(len(report['events']))+'.raw')).write_bytes(raw)
   event.update(ssh_state='returned',ssh_finished_ns=time.time_ns(),ssh_exit_code=p.returncode)
   if not proof_valid(p.stdout.decode(errors='replace'),p.returncode):save();continue
   report.update(native_ssh_verified=True,phone_ip=ip,state='identity-proved',verified_ns=time.time_ns());save();print('PINNED NATIVE SSH VERIFIED:',ip,flush=True)
   token=BUILD['session_token'];ack="printf '%s\\n' '"+token+"' > /run/lynx/host-confirmed.tmp && mv /run/lynx/host-confirmed.tmp /run/lynx/host-confirmed"
   try:
    a=subprocess.run(ssh_command(ip,ack),capture_output=True,timeout=15);(out/'ack.raw').write_bytes(a.stdout+a.stderr);report['fallback_cancel_ack_exit_code']=a.returncode;save()
   except subprocess.TimeoutExpired as e:
    (out/'ack.raw').write_bytes((e.stdout or b'')+(e.stderr or b''));report.update(state='identity-proved-ack-timeout',fallback_cancel_ack_timed_out=True);save();return
   if a.returncode!=0:report['state']='identity-proved-ack-failed';save();return
   try:
    d=subprocess.run(ssh_command(ip,DIAGNOSTICS),capture_output=True,timeout=35);(out/'diagnostics.raw').write_bytes(d.stdout+d.stderr);report['diagnostics_exit_code']=d.returncode
   except subprocess.TimeoutExpired as e:
    (out/'diagnostics.raw').write_bytes((e.stdout or b'')+(e.stderr or b''));report['diagnostics_timed_out']=True
   report['journals']={}
   for owner in ['supervisor','bootstrap','wifi']:
    entry={};report['journals'][owner]=entry
    try:
     j=subprocess.run(ssh_command(ip,'cat /run/lynx/stages-'+owner+'.hex'),capture_output=True,timeout=15)
     (out/(owner+'.hex')).write_bytes(j.stdout);(out/(owner+'-stderr.raw')).write_bytes(j.stderr);entry['retrieval_exit_code']=j.returncode
     if j.returncode==0:
      decoded=decode(j.stdout,BUILD['session_token']);decoded['identity_authenticated']=True
      for record in decoded['records']:record['stage']=BUILD['diagnostic_codebook'].get(str(int(record['stage_hex'],16)),record['stage'])
      (out/(owner+'-decoded.json')).write_text(json.dumps(decoded,indent=2)+'\n');entry.update(records=len(decoded['records']),valid=decoded['complete_sequences_and_checksums'])
    except subprocess.TimeoutExpired as e:
     (out/(owner+'.hex')).write_bytes(e.stdout or b'');(out/(owner+'-stderr.raw')).write_bytes(e.stderr or b'');entry['retrieval_timed_out']=True
    save()
   report['state']='native-ssh-available';save();print('Saved diagnostics:',out,flush=True);return
 report['state']='deadline-without-verified-ssh';report['finished_ns']=time.time_ns();save();print('No verified SSH before deadline:',receipt,flush=True)
if __name__=='__main__':main()
