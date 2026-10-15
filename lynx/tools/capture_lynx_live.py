"""Pinned, read-only live Linux proof and diagnostic archive for working V19."""
import hashlib,json,subprocess,time,tarfile,io
from pathlib import Path
from lynx_wifi_v19_contact import ssh_command,PROOF,proof_valid
R=Path(__file__).resolve().parent.parent
def main():
 ip='192.168.100.9';out=R/'logs'/('native-live-'+str(time.time_ns()));out.mkdir(mode=0o700)
 report={'phone_ip':ip,'started_ns':time.time_ns(),'partition_writes':False,'operations':[]};receipt=out/'result.json'
 def save():receipt.write_text(json.dumps(report,indent=2)+'\n');receipt.chmod(0o600)
 def run(name,command,timeout=30):
  op={'name':name,'started_ns':time.time_ns()};report['operations'].append(op);save()
  try:
   p=subprocess.run(ssh_command(ip,command),capture_output=True,timeout=timeout);stdout,stderr,rc=p.stdout,p.stderr,p.returncode
  except subprocess.TimeoutExpired as ex:
   stdout,stderr,rc=ex.stdout or b'',ex.stderr or b'',None;op['timeout']=True
  for suffix,data in [('stdout',stdout),('stderr',stderr)]:
   f=out/(name+'.'+suffix);f.write_bytes(data);f.chmod(0o600)
  op.update(finished_ns=time.time_ns(),exit_code=rc,stdout_bytes=len(stdout),stdout_sha256=hashlib.sha256(stdout).hexdigest());save();return stdout,rc
 proof,rc=run('proof',PROOF,15);report['identity_verified']=proof_valid(proof.decode(errors='replace'),rc);save()
 if not report['identity_verified']:raise RuntimeError('Pinned identity proof failed; no further commands')
 run('health',"uname -a; cat /proc/uptime /proc/meminfo; ip address show; ip route show; cat /run/lynx/host-confirmed; /sbin/wpa_cli -p /run/wpa_supplicant -i wlan0 status; ps",20)
 # Keep bounded top-level runtime records; omit bulky extracted image payloads.
 archive,rc=run('diagnostics.tar.gz',"set --; for f in /run/lynx/*; do [ -f \"$f\" ] || continue; case \"$f\" in *.gz|*.cpio|*.img|*.bin) continue ;; esac; n=$(stat -c %s \"$f\") || continue; [ \"$n\" -le 8388608 ] || continue; set -- \"$@\" \"$f\"; done; tar -czf - \"$@\"",25)
 if rc==0:
  try:
   with tarfile.open(fileobj=io.BytesIO(archive),mode='r:gz') as tar:
    members=tar.getmembers()
    for member in members:
     if member.isfile():tar.extractfile(member).read()
   report['archive_validated']=True;report['archive_members']=len(members)
  except (tarfile.TarError,EOFError,OSError) as error:report['archive_error']=repr(error)
 save()
 run('dmesg','dmesg',20)
 report['finished_ns']=time.time_ns();save();print(receipt)
if __name__=='__main__':main()
