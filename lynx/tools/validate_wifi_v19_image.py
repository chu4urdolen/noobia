"""Independent delta check: retain all V18 boot/timing/radio safeguards."""
import gzip,hashlib,json,stat,struct,subprocess,sys
from pathlib import Path
R=Path(__file__).resolve().parent.parent;P=R/'linux-port';sys.path.insert(0,str(P))
from image_formats import read_boot_v4,read_newc,require
from ramdisk_codec import decompress
SHA='5ce2dbf8a7c132fa7e31f6be70aa76f83afe8c293e2cd5f02251a532486fd851'
PARENT='62bfed751f3793f63132d2ca3181a5aa869f4f5ce6efcb640abbcaecc9ba4f40'
LAUNCH='947901bd03ca02ab6d23344ea00d64cd552d592f5eb52727948c14cdcd828860'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def main():
 parent=json.loads((P/'docs/wifi-v18-image-validation.json').read_text());require(parent['passed'] and parent['candidate_sha256']==PARENT,'Parent validation differs')
 F=P/'artifacts/busybox-wifi-ssh-twostage-v19';V=P/'artifacts/busybox-wifi-ssh-twostage-v18';raw=(F/'nord3-busybox-candidate.img').read_bytes();old=(V/'nord3-busybox-candidate.img').read_bytes();require(sha(raw)==SHA and sha(old)==PARENT and len(raw)==len(old)==67108864,'Image differs');require(stat.S_IMODE(F.stat().st_mode)==0o700 and stat.S_IMODE((F/'nord3-busybox-candidate.img').stat().st_mode)==0o600,'Private permissions differ')
 b,o=read_boot_v4(raw),read_boot_v4(old);e,p=read_newc(decompress(b['ramdisk'])),read_newc(decompress(o['ramdisk']));require(b['kernel']==o['kernel'] and b['cmdline']==o['cmdline'] and raw[:12]==old[:12] and raw[16:4096]==old[16:4096],'Kernel/header changed');require(set(e)==set(p),'First-stage entry set differs')
 for n in p:
  if n not in ['etc/lynx/session-token','etc/lynx/payload-bytes','etc/lynx/payload-sha256']:require(e[n]==p[n],'Unrelated first-stage change: '+n)
 payload=(F/'supplement.cpio.gz').read_bytes();prev=(V/'supplement.cpio.gz').read_bytes();x,y=read_newc(gzip.decompress(payload)),read_newc(gzip.decompress(prev));require(set(x)-set(y)=={'etc/lynx/wpa-launch.sh'} and not set(y)-set(x),'Supplement entries differ')
 for n in y:
  if n!='etc/lynx/wifi-runtime.sh':require(x[n]==y[n],'Unrelated module/firmware/credential/config change: '+n)
 anchor=b'    /sbin/wpa_supplicant -B -d -D nl80211 -i "$wifi_interface" -c /etc/lynx/wpa_supplicant.conf -f /run/lynx/wpa.log || return 142\n';wifi=y['etc/lynx/wifi-runtime.sh']['data'];require(wifi.count(anchor)==1,'Launch boundary differs');expected=wifi.replace(anchor,b'    . /etc/lynx/wpa-launch.sh || return 142\n    lynx_start_supplicant "$wifi_interface" nl80211 /etc/lynx/wpa_supplicant.conf || return 142\n');require(x['etc/lynx/wifi-runtime.sh']['data']==expected==(F/'wifi-runtime.sh').read_bytes(),'Unexpected runtime change');launch=x['etc/lynx/wpa-launch.sh']['data'];require(sha(launch)==LAUNCH and launch==(P/'wpa-launch.sh').read_bytes() and b' -f /run/' not in launch,'Launcher differs')
 m=json.loads((F/'build-validation.json').read_text());pm=json.loads((V/'build-validation.json').read_text());require(m['candidate_sha256']==SHA and m['wpa_launch_sha256']==LAUNCH,'Manifest differs');require(m['target_delays_seconds']==pm['target_delays_seconds'] and m['timing_runtime_sha256']==pm['timing_runtime_sha256'] and m['observation_seconds']==660,'Timing safeguards changed');require(m['session_token']==e['etc/lynx/session-token']['data'].decode().strip() and m['supplement_sha256']==sha(payload) and e['etc/lynx/payload-sha256']['data']==(sha(payload)+'\n').encode() and e['etc/lynx/payload-bytes']['data']==(str(len(payload))+'\n').encode(),'Payload metadata differs')
 coverage=struct.unpack('!4sIIQQQ28x',old[-64:])[3];off=25165824;require(raw[off:off+len(payload)]==payload and raw[coverage:off]==old[coverage:off] and raw[off+max(len(payload),len(prev)):]==old[off+max(len(payload),len(prev)):],'Protected bytes changed');require(4096+((len(b['kernel'])+4095)//4096)*4096+((len(b['ramdisk'])+4095)//4096)*4096<=coverage,'Metadata overlap')
 native=sorted((P/'artifacts').glob('emulated-wpa-control-pair-*/result.json'))[-1];r=json.loads(native.read_text());require(all(r[k] for k in ['completed','control_pong','status_reply','launch_success','bad_driver_refused','log_captured']) and r['returncode']==0 and not r['timed_out'] and r['launch_source_sha256']==LAUNCH,'Real WPA pair check failed')
 for n in ['sbin/wpa_supplicant','sbin/wpa_cli']:require(r['binary_sha256'][n]==sha(x[n]['data']),'Tested binary differs')
 vendor=sorted((P/'artifacts').glob('emulated-native-vendor-wifi-v19-loop-*/result.json'))[-1];r=json.loads(vendor.read_text());require(r['passed'] and all(r['checks'].values()) and r['candidate_sha256']==SHA,'Payload check failed')
 c=subprocess.run(['python3',str(R/'tools/lynx_wifi_v19_contact.py'),'--self-test'],capture_output=True,text=True,timeout=20);require(c.returncode==0,'Identity proof failed');wrapper=(R/'tools/lynx_boot_a_wifi_v19_trial.py').read_text();require(SHA in wrapper and 'time.monotonic()+660' in wrapper and 'lynx_wpa_timing' in wrapper,'Trial policy differs')
 for unlocked in ['1','0']:
  c=subprocess.run([str(R/'tools/avb-host/avb-boot-model'),str(P/'artifacts/stock-cph2493-August-eu-ota'),str(F/'nord3-busybox-candidate.img'),'0',unlocked],capture_output=True,text=True,timeout=30);require(c.returncode==0 and json.loads(c.stdout)['slot_data_returned']==(unlocked=='1'),'Boot policy differs')
 out=P/'docs/wifi-v19-image-validation.json';out.write_text(json.dumps({'passed':True,'candidate_sha256':SHA,'parent_sha256':PARENT,'receipts':{'real_wpa_pair':str(native),'vendor_payload':str(vendor),'unchanged_timing_and_guard_parent':str(P/'docs/wifi-v18-image-validation.json')},'phone_contacted':False,'limits':'Real WPA IPC on isolated loopback; physical nl80211 association remains unproven. Reuses pinned unchanged first-stage, timing and module guards.'},indent=2)+'\n');print(out)
if __name__=='__main__':main()
