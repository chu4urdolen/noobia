"""Add RAM-only checkpoints to the proven payload reader and directly encode failures."""
import hashlib,json,secrets,struct
from pathlib import Path
from image_formats import read_boot_v4,read_newc,require
from ramdisk_codec import decompress
from network_userspace import put
from prepare_busybox_diagnostics import pack
P=Path(__file__).resolve().parent;F=P/'artifacts/busybox-bootstrap-timing-v1';OUT=P/'artifacts/busybox-payload-timing-v1'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def main():
    require(not OUT.exists(),'Preserve previous artifacts')
    raw=(F/'nord3-busybox-candidate.img').read_bytes();require(sha(raw)=='a9c233c6aefbae80e2e9cd1fabbb1dcda8cdac3119d9ea58bc5e95b73c96802a','Reference changed')
    boot=read_boot_v4(raw);entries=read_newc(decompress(boot['ramdisk']));init=entries['init']['data']
    markers=[(1,b"    candidates=''\n"),(2,b'    [ -b "$device" ] || return 1\n'),(3,b'    [ "$($BB blockdev --getsize64 "$device")" = 67108864 ] || return 1\n'),(4,b'    bytes=$($BB cat /etc/lynx/payload-bytes) || return 1\n'),(5,b'    $BB dd if="$device" of=/run/lynx/payload-blocks bs=4096 skip=6144 count="$blocks" || return 1\n'),(6,b'    actual=$($BB sha256sum /run/lynx/payload.cpio.gz) || return 1\n'),(7,b'    $BB gzip -dc /run/lynx/payload.cpio.gz > /run/lynx/payload.cpio || return 1\n')]
    for code,anchor in markers:
        require(init.count(anchor)==1,'Payload boundary changed: '+str(code))
        init=init.replace(anchor,("    printf '%s\\n' "+str(code)+" > /run/lynx/payload-progress || return 1\n").encode()+anchor)
    old=(P/'lynx-bootstrap-timing-runtime.sh').read_bytes()
    new=old.replace(b'    bt_code=6\n',b'    bt_code=8\n')
    start=new.index(b'        case "$bt_result" in');end=new.index(b'    fi\n',start)
    new=new[:start]+b'''        case "$bt_result" in
            0) bt_code=0 ;;
            154)
                if IFS= read -r bt_payload < /run/lynx/payload-progress; then
                    case "$bt_payload" in 1|2|3|4|5|6|7) bt_code=$bt_payload ;; esac
                fi ;;
        esac
'''+new[end:]
    require(init.count(old)==1,'Runtime boundary changed');init=init.replace(old,new)
    put(entries,'init',init);token=secrets.token_hex(16);put(entries,'etc/lynx/session-token',(token+'\n').encode(),0o100644)
    rd=pack(entries);header=bytearray(raw[:1584]);struct.pack_into('<I',header,12,len(rd));align=lambda n:(n+4095)//4096*4096
    loaded=bytes(header).ljust(4096,b'\0')+boot['kernel'].ljust(align(len(boot['kernel'])),b'\0')+rd.ljust(align(len(rd)),b'\0');coverage=struct.unpack('!4sIIQQQ28x',raw[-64:])[3];require(len(loaded)<=coverage,'Metadata overlap');image=loaded.ljust(coverage,b'\0')+raw[coverage:]
    OUT.mkdir(mode=0o700)
    for name,data in [('nord3-busybox-candidate.img',image),('init-source',init),('runtime-source',new)]:
        path=OUT/name;path.write_bytes(data);path.chmod(0o600)
    runtimepath=P/'lynx-payload-timing-runtime.sh';require(not runtimepath.exists(),'Preserve runtime');runtimepath.write_bytes(new)
    codes={'0':'bootstrap completed: own boot_a payload verified/extracted; no radio','1':'payload failed: candidate enumeration/uniqueness/device name','2':'payload failed: expected block device node absent','3':'payload failed: capacity or read-only block ioctl','4':'payload failed: size/hash metadata validation','5':'payload failed: raw block read or byte trimming','6':'payload failed: SHA256 calculation or mismatch','7':'payload failed: gzip decompression or cpio extraction','8':'other bootstrap failure, deadline or invalid progress'}
    report=json.loads((F/'build-validation.json').read_text());report.update(candidate=str(OUT/'nord3-busybox-candidate.img'),candidate_sha256=sha(image),init_sha256=sha(init),ramdisk_bytes=len(rd),session_token=token,runtime_sha256=sha(new),result_codes=codes,target_delays_seconds={str(i):240+5*i for i in range(9)},observation_seconds=360,payload_step_timing=True)
    (OUT/'build-validation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(candidate_sha256=sha(image),ramdisk_bytes=len(rd)),indent=2))
if __name__=='__main__':main()
