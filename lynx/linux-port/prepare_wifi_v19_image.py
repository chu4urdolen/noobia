"""Fix unsupported WPA log option; require live daemon control readiness."""
import gzip,hashlib,json,secrets,struct
from pathlib import Path
from image_formats import read_boot_v4,read_newc,require
from ramdisk_codec import decompress
from network_userspace import put
from prepare_busybox_diagnostics import pack
P=Path(__file__).resolve().parent;F=P/'artifacts/busybox-wifi-ssh-twostage-v18';OUT=P/'artifacts/busybox-wifi-ssh-twostage-v19'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def main():
 require(not OUT.exists(),'Preserve earlier artifacts')
 raw=(F/'nord3-busybox-candidate.img').read_bytes();require(sha(raw)=='62bfed751f3793f63132d2ca3181a5aa869f4f5ce6efcb640abbcaecc9ba4f40','Parent differs')
 b=read_boot_v4(raw);e=read_newc(decompress(b['ramdisk']));x=read_newc(gzip.decompress((F/'supplement.cpio.gz').read_bytes()))
 launch=(P/'wpa-launch.sh').read_bytes();put(x,'etc/lynx/wpa-launch.sh',launch,0o100644)
 wifi=x['etc/lynx/wifi-runtime.sh']['data'];anchor=b'    /sbin/wpa_supplicant -B -d -D nl80211 -i "$wifi_interface" -c /etc/lynx/wpa_supplicant.conf -f /run/lynx/wpa.log || return 142\n';require(wifi.count(anchor)==1,'Launch boundary differs')
 wifi=wifi.replace(anchor,b'    . /etc/lynx/wpa-launch.sh || return 142\n    lynx_start_supplicant "$wifi_interface" nl80211 /etc/lynx/wpa_supplicant.conf || return 142\n');put(x,'etc/lynx/wifi-runtime.sh',wifi,0o100644)
 payload=gzip.compress(decompress(pack(x)),mtime=0);put(e,'etc/lynx/payload-bytes',(str(len(payload))+'\n').encode(),0o100644);put(e,'etc/lynx/payload-sha256',(sha(payload)+'\n').encode(),0o100644);token=secrets.token_hex(16);put(e,'etc/lynx/session-token',(token+'\n').encode(),0o100644)
 rd=pack(e);h=bytearray(raw[:1584]);struct.pack_into('<I',h,12,len(rd));align=lambda n:(n+4095)//4096*4096;loaded=bytes(h).ljust(4096,b'\0')+b['kernel'].ljust(align(len(b['kernel'])),b'\0')+rd.ljust(align(len(rd)),b'\0');coverage=struct.unpack('!4sIIQQQ28x',raw[-64:])[3];require(len(loaded)<=coverage,'Metadata overlap');image=bytearray(loaded.ljust(coverage,b'\0')+raw[coverage:]);offset=25165824;prev=(F/'supplement.cpio.gz').read_bytes();require(offset+len(payload)<len(image)-4096,'Payload overlap');image[offset:offset+max(len(payload),len(prev))]=payload.ljust(max(len(payload),len(prev)),b'\0');image=bytes(image);OUT.mkdir(mode=0o700)
 for name,data in [('nord3-busybox-candidate.img',image),('init-source',e['init']['data']),('timing-runtime-source',e['bin/boot-proof-reboot']['data']),('supplement.cpio.gz',payload),('wifi-runtime.sh',wifi),('wpa-launch.sh',launch)]:
  f=OUT/name;f.write_bytes(data);f.chmod(0o600)
 m=json.loads((F/'build-validation.json').read_text());m.update(candidate=str(OUT/'nord3-busybox-candidate.img'),candidate_sha256=sha(image),ramdisk_bytes=len(rd),session_token=token,supplement_bytes=len(payload),supplement_sha256=sha(payload),supplement_entry_names=list(x),wpa_launch_sha256=sha(launch),diagnostic_version='v19 real WPA daemon/control readiness',parent_sha256=sha(raw),phone_contacted=False,flash_eligible=False)
 (OUT/'build-validation.json').write_text(json.dumps(m,indent=2)+'\n');print(json.dumps({'candidate_sha256':sha(image),'ramdisk_bytes':len(rd),'supplement_bytes':len(payload)},indent=2))
if __name__=='__main__':main()
