"""Keep V16 radio service; record each own-boot payload operation separately."""
import hashlib,json,secrets,struct
from pathlib import Path
from image_formats import read_boot_v4,read_newc,require
from ramdisk_codec import decompress
from network_userspace import put
from prepare_busybox_diagnostics import pack
P=Path(__file__).resolve().parent;F=P/'artifacts/busybox-wifi-ssh-twostage-v16';OUT=P/'artifacts/busybox-wifi-ssh-twostage-v17'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def main():
    require(not OUT.exists(),'Preserve prior artifacts')
    raw=(F/'nord3-busybox-candidate.img').read_bytes();require(sha(raw)=='73311e9613a002a5bf3d3d4c4b5057840b7a427a06e1aff18a186e27e68614f6','Parent changed');b=read_boot_v4(raw);e=read_newc(decompress(b['ramdisk']));init=e['init']['data']
    helper=b'''lynx_payload_step() {
    printf '%s\\n' "$1" > /run/lynx/payload-step
}
'''
    anchor=b'lynx_read_own_boot_payload() {\n';require(init.count(anchor)==1,'Reader anchor changed');init=init.replace(anchor,helper+anchor+b'    lynx_payload_step 1 || return 1\n')
    anchors=[b'    device=/dev/$1\n',b'    [ "$($BB blockdev --getsize64 "$device")" = 67108864 ]',b'    $BB blockdev --setro "$device"',b'    bytes=$($BB cat /etc/lynx/payload-bytes)',b'    blocks=$(((bytes+4095)/4096))',b'    actual=$($BB sha256sum /run/lynx/payload.cpio.gz)',b'    $BB gzip -dc /run/lynx/payload.cpio.gz',b'    (cd / && $BB cpio -idmu < /run/lynx/payload.cpio)',b'    log "BOOT_A_SUPPLEMENT_VERIFIED_AND_EXTRACTED']
    for step,anchor in enumerate(anchors,2):
        require(init.count(anchor)==1,'Payload boundary changed: '+str(step));init=init.replace(anchor,('    lynx_payload_step '+str(step)+' || return 1\n').encode()+anchor)
    put(e,'init',init)
    timing=e['bin/boot-proof-reboot']['data'];anchor=b'            151|152|153|154) nt_code=$((nt_boot-131)) ;;\n';require(timing.count(anchor)==1,'Bootstrap mapping changed')
    timing=timing.replace(anchor,b'''            154)
                nt_code=23
                if IFS= read -r nt_payload < /run/lynx/payload-step; then
                    case "$nt_payload" in 1|2|3|4|5|6|7|8|9|10) nt_code=$((39+nt_payload)) ;; esac
                fi ;;
            151|152|153) nt_code=$((nt_boot-131)) ;;
''').replace(b'nt_target=$((120+5*nt_code))',b'nt_target=$((80+5*nt_code))');put(e,'bin/boot-proof-reboot',timing)
    token=secrets.token_hex(16);put(e,'etc/lynx/session-token',(token+'\n').encode(),0o100644);rd=pack(e);h=bytearray(raw[:1584]);struct.pack_into('<I',h,12,len(rd));align=lambda n:(n+4095)//4096*4096
    loaded=bytes(h).ljust(4096,b'\0')+b['kernel'].ljust(align(len(b['kernel'])),b'\0')+rd.ljust(align(len(rd)),b'\0');coverage=struct.unpack('!4sIIQQQ28x',raw[-64:])[3];require(len(loaded)<=coverage,'Metadata overlap');image=loaded.ljust(coverage,b'\0')+raw[coverage:];OUT.mkdir(mode=0o700)
    for name,data in [('nord3-busybox-candidate.img',image),('init-source',init),('timing-runtime-source',timing),('supplement.cpio.gz',(F/'supplement.cpio.gz').read_bytes())]:
        f=OUT/name;f.write_bytes(data);f.chmod(0o600)
    labels=['own boot partition discovery failed','own boot block node missing','own boot block size check failed','own boot read-only setup failed','payload size/hash metadata invalid','payload block read or bounded copy failed','payload SHA256 verification failed','payload gzip decompression failed','payload cpio extraction failed','payload extracted; final completion log failed']
    m=json.loads((F/'build-validation.json').read_text());m['result_codes'].update({str(i):label for i,label in enumerate(labels,40)});m.update(candidate=str(OUT/'nord3-busybox-candidate.img'),candidate_sha256=sha(image),ramdisk_bytes=len(rd),session_token=token,init_sha256=sha(init),timing_runtime_sha256=sha(timing),target_delays_seconds={str(n):525 if n==9 else 80+5*n for n in range(50)},diagnostic_version='v17 payload substeps and early margin-guarded slots',parent_sha256=sha(raw),phone_contacted=False,flash_eligible=False)
    (OUT/'build-validation.json').write_text(json.dumps(m,indent=2)+'\n');print(json.dumps({'candidate_sha256':sha(image),'ramdisk_bytes':len(rd)},indent=2))
if __name__=='__main__':main()
