"""Add a bounded read-only worker stack snapshot after the one station attempt."""
import gzip,hashlib,json,secrets,struct
from pathlib import Path
from image_formats import read_boot_v4,read_newc,require
from ramdisk_codec import decompress
from network_userspace import put
from prepare_busybox_diagnostics import pack
P=Path(__file__).resolve().parent;F=P/'artifacts/busybox-wifi-ssh-twostage-v13';OUT=P/'artifacts/busybox-wifi-ssh-twostage-v14'
STUB=b'''# Parser lives in the verified supplemental RAM archive.
lynx_station_failure_code() {
    nt_station_code=34
    . /etc/lynx/power-stack-parser.sh || return 0
    lynx_stack_failure_code
}
'''
def sha(raw):return hashlib.sha256(raw).hexdigest()
def main():
    require(not OUT.exists(),'Preserve prior images')
    raw=(F/'nord3-busybox-candidate.img').read_bytes();require(sha(raw)=='3b7d7962c8526e01b60f953f5f6b660e10cc6d599f7539d290f03857147165bb','Parent changed')
    b=read_boot_v4(raw);e=read_newc(decompress(b['ramdisk']));x=read_newc(gzip.decompress((F/'supplement.cpio.gz').read_bytes()))
    parent=(F/'power-failure-parser.sh').read_bytes();parser=parent.replace(b'lynx_station_failure_code()',b'lynx_power_failure_code()')+(P/'power-stack-parser.sh').read_bytes();capture=(P/'wifi-worker-stack.sh').read_bytes()
    put(x,'etc/lynx/power-stack-parser.sh',parser,0o100644);put(x,'etc/lynx/wifi-worker-stack.sh',capture,0o100644)
    wifi=x['etc/lynx/wifi-runtime.sh']['data'];anchor=b'        $BB dmesg | $BB tail -c 1048576 > /run/lynx/station-dmesg\n';require(wifi.count(anchor)==1,'Snapshot boundary changed')
    wifi=wifi.replace(anchor,anchor+b'        if . /etc/lynx/wifi-worker-stack.sh; then lynx_capture_wifi_worker_stack; fi\n');put(x,'etc/lynx/wifi-runtime.sh',wifi,0o100644)
    payload=gzip.compress(decompress(pack(x)),mtime=0)
    timing=e['bin/boot-proof-reboot']['data'];require(timing.count(parent)==1,'Timing boundary changed');timing=timing.replace(parent,STUB);put(e,'bin/boot-proof-reboot',timing)
    put(e,'etc/lynx/payload-bytes',(str(len(payload))+'\n').encode(),0o100644);put(e,'etc/lynx/payload-sha256',(sha(payload)+'\n').encode(),0o100644)
    token=secrets.token_hex(16);put(e,'etc/lynx/session-token',(token+'\n').encode(),0o100644)
    rd=pack(e);header=bytearray(raw[:1584]);struct.pack_into('<I',header,12,len(rd));align=lambda n:(n+4095)//4096*4096
    loaded=bytes(header).ljust(4096,b'\0')+b['kernel'].ljust(align(len(b['kernel'])),b'\0')+rd.ljust(align(len(rd)),b'\0');coverage=struct.unpack('!4sIIQQQ28x',raw[-64:])[3];require(len(loaded)<=coverage,'Metadata overlap')
    image=bytearray(loaded.ljust(coverage,b'\0')+raw[coverage:]);offset=25165824;oldpayload=(F/'supplement.cpio.gz').read_bytes();require(offset+len(payload)<len(image)-4096,'Payload overlap')
    image[offset:offset+max(len(payload),len(oldpayload))]=payload.ljust(max(len(payload),len(oldpayload)),b'\0');image=bytes(image)
    OUT.mkdir(mode=0o700)
    for name,data in [('nord3-busybox-candidate.img',image),('timing-runtime-source',timing),('init-source',e['init']['data']),('supplement.cpio.gz',payload),('wifi-runtime.sh',wifi),('power-stack-parser.sh',parser),('wifi-worker-stack.sh',capture),('diag-hooks.sh',(F/'diag-hooks.sh').read_bytes())]:
        f=OUT/name;f.write_bytes(data);f.chmod(0o600)
    m=json.loads((F/'build-validation.json').read_text());codes=m['result_codes'];labels=['worker at exact stock pre-calibration sleep return site','worker stack includes wlanProbe','worker stack includes firmware loader','worker stack includes connectivity power functions','worker stack includes another wait','worker stack readable; no recognized site','Wi-Fi worker absent','Wi-Fi worker ambiguous','Wi-Fi worker stack unavailable','current marked power-timeout evidence absent','reserved diagnostic fallback']
    codes.update({str(i):v for i,v in enumerate(labels,25)})
    m.update(candidate=str(OUT/'nord3-busybox-candidate.img'),candidate_sha256=sha(image),ramdisk_bytes=len(rd),session_token=token,supplement_bytes=len(payload),supplement_sha256=sha(payload),supplement_entry_names=list(x),timing_runtime_sha256=sha(timing),station_parser_sha256=sha(parser),worker_stack_capture_sha256=sha(capture),result_codes=codes,diagnostic_version='v14 worker procfs snapshot',parent_sha256=sha(raw),phone_contacted=False,flash_eligible=False)
    (OUT/'build-validation.json').write_text(json.dumps(m,indent=2)+'\n');print(json.dumps({'candidate_sha256':sha(image),'ramdisk_bytes':len(rd),'supplement_bytes':len(payload)},indent=2))
if __name__=='__main__':main()
