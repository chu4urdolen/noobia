"""Storage/bootstrap plus ordered read-only driver-registration profile."""
import hashlib
import json
import secrets
import struct
from pathlib import Path
from image_formats import read_boot_v4,read_newc,require
from ramdisk_codec import decompress
from prepare_busybox_diagnostics import pack
from network_userspace import put

P=Path(__file__).resolve().parent
F=P/'artifacts/busybox-storage-outcome-v2'
OUT=P/'artifacts/busybox-binding-profile-v1'


def main():
    require(not OUT.exists(),'Preserve prior profile')
    data=(F/'nord3-busybox-candidate.img').read_bytes()
    require(hashlib.sha256(data).hexdigest()=='5f85ae811386ccec50c1eab94649f587621035ca053126788d9627ee666bea25','Reference changed')
    boot=read_boot_v4(data);entries=read_newc(decompress(boot['ramdisk']))
    old=(P/'lynx-storage-outcome-runtime.sh').read_bytes()
    profile=(P/'lynx-binding-profile.sh').read_bytes()
    start=old.index(b'        probe_code=8\n')
    end=old.index(b"        printf '%s %s\\n'",start)
    selector=b'''        probe_code=8
        case "$probe_status" in
            0|153)
                lynx_binding_profile
                probe_code=$?
                case "$probe_code" in 1|2|3|4|5|6|7) ;; *) probe_code=8 ;; esac
                ;;
        esac
'''
    runtime=profile+old[:start]+selector+old[end:]
    runtime=runtime.replace(b'1|2|3|4|5|6|8)',b'1|2|3|4|5|6|7|8)',1)
    runtime=runtime.replace(b'            probe_code=7\n',b'            probe_code=8\n',1)
    init=entries['init']['data'];require(init.count(old)==1,'Runtime boundary changed')
    init=init.replace(old,runtime,1);put(entries,'init',init)
    token=secrets.token_hex(16);put(entries,'etc/lynx/session-token',(token+'\n').encode(),0o100644)
    ramdisk=pack(entries);header=bytearray(data[:1584]);struct.pack_into('<I',header,12,len(ramdisk))
    align=lambda n:(n+4095)//4096*4096
    loaded=bytes(header).ljust(4096,b'\0')+boot['kernel'].ljust(align(len(boot['kernel'])),b'\0')+ramdisk.ljust(align(len(ramdisk)),b'\0')
    coverage=struct.unpack('!4sIIQQQ28x',data[-64:])[3]
    require(len(loaded)<=coverage,'Original loaded-area bound exceeded')
    image=loaded.ljust(coverage,b'\0')+data[coverage:]
    require(len(image)==len(data) and image[coverage:]==data[coverage:],'Outside initramfs changed')
    OUT.mkdir(mode=0o700)
    for name,raw in [('nord3-busybox-candidate.img',image),('init-source',init),('profile-runtime.sh',runtime)]:
        file=OUT/name;file.write_bytes(raw);file.chmod(0o600)
    report=json.loads((F/'build-validation.json').read_text())
    meanings={1:'kernel command line does not contain fw_devlink=permissive',
              2:'expected ufshcd-mtk platform driver not registered',
              3:'expected UFS platform device not present',
              4:'first stock syscon reset supplier not bound to ti-syscon-reset',
              5:'VEMC regulator name absent from regulator class',
              6:'UFS device reports waiting_for_supplier=1',
              7:'option, driver, UFS device, first reset and VEMC present; no waiting-supplier flag',
              8:'bootstrap failed before profile or timed out; no profile result'}
    report.update(candidate=str(OUT/'nord3-busybox-candidate.img'),candidate_sha256=hashlib.sha256(image).hexdigest(),init_sha256=hashlib.sha256(init).hexdigest(),
                  ramdisk_bytes=len(ramdisk),session_token=token,runtime_sha256=hashlib.sha256(runtime).hexdigest(),result_codes={str(k):v for k,v in meanings.items()},
                  profile_source_sha256=hashlib.sha256(profile).hexdigest(),phone_contacted=False,flash_eligible=False)
    (OUT/'build-validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ['candidate','candidate_sha256','ramdisk_bytes']},indent=2))


if __name__=='__main__':main()
