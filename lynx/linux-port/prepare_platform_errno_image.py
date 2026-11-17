"""Build the exact-errno diagnostic, preserving the stock undo and prior trials."""
import hashlib,json,secrets,struct
from pathlib import Path
from image_formats import read_boot_v4,read_newc,require
from ramdisk_codec import decompress
from network_userspace import put
from prepare_busybox_diagnostics import pack

P=Path(__file__).resolve().parent;F=P/'artifacts/busybox-platform-probe-v1';OUT=P/'artifacts/busybox-platform-errno-v1'


def main():
    require(not OUT.exists(),'Preserve earlier candidate')
    data=(F/'nord3-busybox-candidate.img').read_bytes();require(hashlib.sha256(data).hexdigest()=='aff51e9e74094d95fa0e2addbf3671326869a07eda2104f09b28821f8b07f56f','Reference changed')
    boot=read_boot_v4(data);entries=read_newc(decompress(boot['ramdisk']))
    old=(F/'trace-runtime.sh').read_bytes();collector=(P/'lynx-driver-trace-platform-v2.sh').read_bytes()
    helper=(P/'lynx-live-ufs-name.sh').read_bytes();control=(P/'lynx-platform-errno-runtime.sh').read_bytes();classifier=(P/'lynx-classify-platform-errno.awk').read_bytes()
    runtime=collector+helper+control;init=entries['init']['data'];require(init.count(old)==1,'Runtime boundary changed')
    init=init.replace(old,runtime,1);put(entries,'init',init);put(entries,'etc/lynx/classify-driver-trace.awk',classifier,0o100644)
    token=secrets.token_hex(16);put(entries,'etc/lynx/session-token',(token+'\n').encode(),0o100644)
    ramdisk=pack(entries);header=bytearray(data[:1584]);struct.pack_into('<I',header,12,len(ramdisk))
    align=lambda n:(n+4095)//4096*4096
    loaded=bytes(header).ljust(4096,b'\0')+boot['kernel'].ljust(align(len(boot['kernel'])),b'\0')+ramdisk.ljust(align(len(ramdisk)),b'\0')
    coverage=struct.unpack('!4sIIQQQ28x',data[-64:])[3];require(len(loaded)<=coverage,'Original loaded area exceeded')
    image=loaded.ljust(coverage,b'\0')+data[coverage:];require(len(image)==len(data) and image[coverage:]==data[coverage:],'Metadata/supplement changed')
    OUT.mkdir(mode=0o700)
    for name,raw in [('nord3-busybox-candidate.img',image),('init-source',init),('trace-runtime.sh',runtime),('collector-source.sh',collector)]:
        path=OUT/name;path.write_bytes(raw);path.chmod(0o600)
    codes={str(n):'platform wrapper returned '+str(-n) for n in range(1,121)}
    codes.update({'0':'platform wrapper returned zero; not final binding proof','121':'platform wrapper returned -517 (EPROBE_DEFER)',
                  '122':'platform wrapper returned a negative errno outside encoded range','123':'platform wrapper returned positive',
                  '124':'live target or completed platform return unavailable','125':'fresh PID trace health absent',
                  '126':'trace setup/capture/correlation unavailable','127':'bootstrap worker deadline'})
    report=json.loads((F/'build-validation.json').read_text())
    report.update(candidate=str(OUT/'nord3-busybox-candidate.img'),candidate_sha256=hashlib.sha256(image).hexdigest(),init_sha256=hashlib.sha256(init).hexdigest(),
                  ramdisk_bytes=len(ramdisk),session_token=token,runtime_sha256=hashlib.sha256(runtime).hexdigest(),classifier_sha256=hashlib.sha256(classifier).hexdigest(),
                  live_name_source_sha256=hashlib.sha256(helper).hexdigest(),result_codes=codes,target_delays_seconds={str(n):60+2*n for n in range(128)},
                  baseline_reference_seconds=21.9,timing_match_tolerance_seconds=0.8,observation_seconds=380,phone_contacted=False,flash_eligible=False,
                  baseline_evidence=['boot-a-core-probe-trial-1791907590015628810.json','boot-a-match-profile-trial-1791909079698893610.json'],
                  timing_limits='Finer timing is indirect and may reject variable-latency boots; decode only within0.8seconds and with reset/non-interference evidence.')
    (OUT/'build-validation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:report[k] for k in ['candidate_sha256','ramdisk_bytes','flash_eligible']},indent=2))


if __name__=='__main__':main()
