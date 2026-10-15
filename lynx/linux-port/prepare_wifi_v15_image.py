"""Await verified asynchronous completion; accelerate unambiguous result slots."""
import gzip,hashlib,json,secrets,struct
from pathlib import Path
from image_formats import read_boot_v4,read_newc,require
from ramdisk_codec import decompress
from network_userspace import put
from prepare_busybox_diagnostics import pack
P=Path(__file__).resolve().parent;F=P/'artifacts/busybox-wifi-ssh-twostage-v14';OUT=P/'artifacts/busybox-wifi-ssh-twostage-v15'
FAST_TIMING=b'''    nt_target=$((120+5*nt_code))
    [ "$nt_code" != 9 ] || nt_target=525
    lynx_network_timing_clock || return 1
    if [ "$nt_seconds" -ge "$((nt_start+nt_target-3))" ]; then
        nt_code=9
        nt_target=525
    fi
    [ "$nt_seconds" -lt "$((nt_start+nt_target-3))" ] || return 1
'''
def sha(raw):return hashlib.sha256(raw).hexdigest()
def main():
    require(not OUT.exists(),'Preserve earlier images')
    raw=(F/'nord3-busybox-candidate.img').read_bytes();require(sha(raw)=='5bc287a9fea447edfe83eeb284d8371ea0ac093f3a17f74e3db66bb171cedded','Parent changed')
    b=read_boot_v4(raw);e=read_newc(decompress(b['ramdisk']));x=read_newc(gzip.decompress((F/'supplement.cpio.gz').read_bytes()))
    ready=(P/'wifi-async-ready.sh').read_bytes();station=(P/'wifi-station-async.sh').read_bytes()
    put(x,'etc/lynx/wifi-async-ready.sh',ready,0o100644);put(x,'etc/lynx/wifi-station-async.sh',station,0o100644)
    wifi=x['etc/lynx/wifi-runtime.sh']['data'];start=wifi.index(b'    station_token=');end=wifi.index(b'    lynx_stage WLAN_INTERFACE_WAIT\n',start)
    wifi=wifi[:start]+b'    . /etc/lynx/wifi-station-async.sh || return 139\n    lynx_wifi_station_request || return 139\n'+wifi[end:];put(x,'etc/lynx/wifi-runtime.sh',wifi,0o100644)
    payload=gzip.compress(decompress(pack(x)),mtime=0)
    timing=e['bin/boot-proof-reboot']['data'];anchor=b'    nt_target=$((480+5*nt_code))\n';require(timing.count(anchor)==1,'Timing anchor changed');timing=timing.replace(anchor,FAST_TIMING);put(e,'bin/boot-proof-reboot',timing)
    put(e,'etc/lynx/payload-bytes',(str(len(payload))+'\n').encode(),0o100644);put(e,'etc/lynx/payload-sha256',(sha(payload)+'\n').encode(),0o100644);token=secrets.token_hex(16);put(e,'etc/lynx/session-token',(token+'\n').encode(),0o100644)
    rd=pack(e);header=bytearray(raw[:1584]);struct.pack_into('<I',header,12,len(rd));align=lambda n:(n+4095)//4096*4096
    loaded=bytes(header).ljust(4096,b'\0')+b['kernel'].ljust(align(len(b['kernel'])),b'\0')+rd.ljust(align(len(rd)),b'\0');coverage=struct.unpack('!4sIIQQQ28x',raw[-64:])[3];require(len(loaded)<=coverage,'Metadata overlap')
    image=bytearray(loaded.ljust(coverage,b'\0')+raw[coverage:]);offset=25165824;previous=(F/'supplement.cpio.gz').read_bytes();require(offset+len(payload)<len(image)-4096,'Payload overlap');image[offset:offset+max(len(payload),len(previous))]=payload.ljust(max(len(payload),len(previous)),b'\0');image=bytes(image)
    OUT.mkdir(mode=0o700)
    for name,data in [('nord3-busybox-candidate.img',image),('timing-runtime-source',timing),('init-source',e['init']['data']),('supplement.cpio.gz',payload),('wifi-runtime.sh',wifi),('wifi-async-ready.sh',ready),('wifi-station-async.sh',station),('power-stack-parser.sh',(F/'power-stack-parser.sh').read_bytes()),('wifi-worker-stack.sh',(F/'wifi-worker-stack.sh').read_bytes()),('diag-hooks.sh',(F/'diag-hooks.sh').read_bytes())]:
        f=OUT/name;f.write_bytes(data);f.chmod(0o600)
    m=json.loads((F/'build-validation.json').read_text());m['result_codes']['9']='Outcome missed its early slot; detailed timing result unavailable'
    m.update(candidate=str(OUT/'nord3-busybox-candidate.img'),candidate_sha256=sha(image),ramdisk_bytes=len(rd),session_token=token,supplement_bytes=len(payload),supplement_sha256=sha(payload),supplement_entry_names=list(x),timing_runtime_sha256=sha(timing),async_ready_sha256=sha(ready),station_request_sha256=sha(station),diagnostic_version='v15 asynchronous completion and early reporting',parent_sha256=sha(raw),target_delays_seconds={str(n):525 if n==9 else 120+5*n for n in range(40)},observation_seconds=660,phone_contacted=False,flash_eligible=False)
    (OUT/'build-validation.json').write_text(json.dumps(m,indent=2)+'\n');print(json.dumps({'candidate_sha256':sha(image),'ramdisk_bytes':len(rd),'supplement_bytes':len(payload)},indent=2))
if __name__=='__main__':main()
