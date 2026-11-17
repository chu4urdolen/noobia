"""Add the existing BusyBox firmware-event daemon before stock radio modules."""
import gzip,hashlib,json,secrets,struct
from pathlib import Path
from image_formats import read_boot_v4,read_newc,require
from ramdisk_codec import decompress
from network_userspace import put
from prepare_busybox_diagnostics import pack
P=Path(__file__).resolve().parent;F=P/'artifacts/busybox-wifi-ssh-twostage-v15';OUT=P/'artifacts/busybox-wifi-ssh-twostage-v16'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def main():
    require(not OUT.exists(),'Preserve prior images')
    raw=(F/'nord3-busybox-candidate.img').read_bytes();require(sha(raw)=='c08d19beb54ef6400912651539d6ce9f510632a94d04180f30b88114d48768f2','Parent changed')
    b=read_boot_v4(raw);e=read_newc(decompress(b['ramdisk']));x=read_newc(gzip.decompress((F/'supplement.cpio.gz').read_bytes()));service=(P/'firmware-events.sh').read_bytes();put(x,'etc/lynx/firmware-events.sh',service,0o100644)
    wifi=x['etc/lynx/wifi-runtime.sh']['data'];anchor=b'    lynx_stage WIFI_DRIVERS\n';require(wifi.count(anchor)==1,'Radio boundary changed')
    wifi=wifi.replace(anchor,b'    . /etc/lynx/firmware-events.sh || return 135\n    lynx_firmware_events_start || return 135\n'+anchor);put(x,'etc/lynx/wifi-runtime.sh',wifi,0o100644);payload=gzip.compress(decompress(pack(x)),mtime=0)
    put(e,'etc/lynx/payload-bytes',(str(len(payload))+'\n').encode(),0o100644);put(e,'etc/lynx/payload-sha256',(sha(payload)+'\n').encode(),0o100644);token=secrets.token_hex(16);put(e,'etc/lynx/session-token',(token+'\n').encode(),0o100644)
    rd=pack(e);header=bytearray(raw[:1584]);struct.pack_into('<I',header,12,len(rd));align=lambda n:(n+4095)//4096*4096;loaded=bytes(header).ljust(4096,b'\0')+b['kernel'].ljust(align(len(b['kernel'])),b'\0')+rd.ljust(align(len(rd)),b'\0');coverage=struct.unpack('!4sIIQQQ28x',raw[-64:])[3];require(len(loaded)<=coverage,'Metadata overlap')
    image=bytearray(loaded.ljust(coverage,b'\0')+raw[coverage:]);offset=25165824;oldpayload=(F/'supplement.cpio.gz').read_bytes();require(offset+len(payload)<len(image)-4096,'Payload overlap');image[offset:offset+max(len(payload),len(oldpayload))]=payload.ljust(max(len(payload),len(oldpayload)),b'\0');image=bytes(image);OUT.mkdir(mode=0o700)
    for name,data in [('nord3-busybox-candidate.img',image),('init-source',e['init']['data']),('timing-runtime-source',e['bin/boot-proof-reboot']['data']),('supplement.cpio.gz',payload),('wifi-runtime.sh',wifi),('firmware-events.sh',service)]:
        f=OUT/name;f.write_bytes(data);f.chmod(0o600)
    m=json.loads((F/'build-validation.json').read_text());m['result_codes']['5']='radio startup failed: module, firmware-service or unclassified clock guard'
    m.update(candidate=str(OUT/'nord3-busybox-candidate.img'),candidate_sha256=sha(image),ramdisk_bytes=len(rd),session_token=token,supplement_bytes=len(payload),supplement_sha256=sha(payload),supplement_entry_names=list(x),firmware_events_sha256=sha(service),diagnostic_version='v16 stock firmware hotplug service',parent_sha256=sha(raw),phone_contacted=False,flash_eligible=False)
    (OUT/'build-validation.json').write_text(json.dumps(m,indent=2)+'\n');print(json.dumps({'candidate_sha256':sha(image),'ramdisk_bytes':len(rd),'supplement_bytes':len(payload)},indent=2))
if __name__=='__main__':main()
