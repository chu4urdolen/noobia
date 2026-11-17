"""Offline storage-only trace candidate, using one bounded result-code return."""
import hashlib,json,secrets,struct
from pathlib import Path
from image_formats import read_boot_v4,read_newc,require
from ramdisk_codec import decompress
from network_userspace import put
from prepare_busybox_diagnostics import pack

P=Path(__file__).resolve().parent
F=P/'artifacts/busybox-storage-outcome-v2'
OUT=P/'artifacts/busybox-probe-trace-v1'


def main():
    require(not OUT.exists(),'Keep prior traces/candidates immutable')
    data=(F/'nord3-busybox-candidate.img').read_bytes()
    require(hashlib.sha256(data).hexdigest()=='5f85ae811386ccec50c1eab94649f587621035ca053126788d9627ee666bea25','Reference changed')
    boot=read_boot_v4(data);entries=read_newc(decompress(boot['ramdisk']))
    old=(P/'lynx-storage-outcome-runtime.sh').read_bytes()
    trace=(P/'lynx-driver-trace.sh').read_bytes()
    classifier=(P/'lynx-classify-driver-trace.awk').read_bytes()
    runtime=old
    marker=b'        lynx_wifi_bootstrap_child\n'
    require(runtime.count(marker)==1,'Child boundary changed')
    runtime=runtime.replace(marker,b'''        trace_ready=0
        if lynx_driver_trace_setup; then trace_ready=1; fi
'''+marker,1)
    start=runtime.index(b'        probe_code=8\n')
    end=runtime.index(b"        printf '%s %s\\n'",start)
    selector=b'''        probe_code=8
        if [ "$trace_ready" != 1 ]; then
            probe_code=1
        elif lynx_driver_trace_capture; then
            $BB awk -f /etc/lynx/classify-driver-trace.awk /run/lynx/driver-trace.log > /run/lynx/driver-trace-result
            if IFS=' ' read -r probe_code trace_ufs_count trace_ufs_ret trace_domain_count trace_domain_ret trace_unpaired trace_malformed trace_unfinished < /run/lynx/driver-trace-result; then
                case "$probe_code" in 2|3|4|5|6|7|8) ;; *) probe_code=8 ;; esac
                log "TRACE_CLASSIFIED code=$probe_code ufs_count=$trace_ufs_count ufs_ret=$trace_ufs_ret domain_count=$trace_domain_count domain_ret=$trace_domain_ret unpaired=$trace_unpaired malformed=$trace_malformed unfinished=$trace_unfinished"
            else probe_code=8; fi
        fi
'''
    runtime=trace+runtime[:start]+selector+runtime[end:]
    runtime=runtime.replace(b'1|2|3|4|5|6|8)',b'1|2|3|4|5|6|7|8)',1)
    runtime=runtime.replace(b'            probe_code=7\n',b'            probe_code=8\n',1)
    init=entries['init']['data'];require(init.count(old)==1,'Init runtime changed')
    init=init.replace(old,runtime,1);put(entries,'init',init)
    put(entries,'etc/lynx/classify-driver-trace.awk',classifier,0o100644)
    token=secrets.token_hex(16);put(entries,'etc/lynx/session-token',(token+'\n').encode(),0o100644)
    ramdisk=pack(entries);header=bytearray(data[:1584]);struct.pack_into('<I',header,12,len(ramdisk))
    align=lambda n:(n+4095)//4096*4096
    loaded=bytes(header).ljust(4096,b'\0')+boot['kernel'].ljust(align(len(boot['kernel'])),b'\0')+ramdisk.ljust(align(len(ramdisk)),b'\0')
    coverage=struct.unpack('!4sIIQQQ28x',data[-64:])[3]
    require(len(loaded)<=coverage,'Original loaded area exceeded')
    image=loaded.ljust(coverage,b'\0')+data[coverage:]
    require(len(image)==len(data) and image[coverage:]==data[coverage:],'Supplement/metadata/footer changed')
    OUT.mkdir(mode=0o700)
    for name,raw in [('nord3-busybox-candidate.img',image),('init-source',init),('trace-runtime.sh',runtime)]:
        target=OUT/name;target.write_bytes(raw);target.chmod(0o600)
    codes={1:'standard trace setup unavailable',2:'UFS core initialization returned EPROBE_DEFER (-517)',
           3:'matched UFS PM-domain attach returned a negative error before a completed UFS core call',
           4:'UFS core returned EINVAL/ENODEV/ENOENT configuration or lookup error',
           5:'UFS core returned ETIMEDOUT/EIO hardware or link error',6:'UFS core returned another nonzero value',
           7:'last completed UFS core initialization returned success',
           8:'no completed UFS return/error classification, capture failure or bootstrap timeout'}
    report=json.loads((F/'build-validation.json').read_text())
    report.update(candidate=str(OUT/'nord3-busybox-candidate.img'),candidate_sha256=hashlib.sha256(image).hexdigest(),init_sha256=hashlib.sha256(init).hexdigest(),
                  ramdisk_bytes=len(ramdisk),session_token=token,runtime_sha256=hashlib.sha256(runtime).hexdigest(),
                  trace_source_sha256=hashlib.sha256(trace).hexdigest(),classifier_sha256=hashlib.sha256(classifier).hexdigest(),
                  result_codes={str(k):v for k,v in codes.items()},phone_contacted=False,flash_eligible=False,
                  limits=['Raw trace/dmesg kept in RAM; after-reboot retrieval still unverified.',
                          'One coarse timing result; no direct authenticated connection.',
                          'Normal kernel instrumentation only, no return-value changes or persistent kernel/bootloader changes.'])
    (OUT/'build-validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ['candidate','candidate_sha256','ramdisk_bytes']},indent=2))


if __name__=='__main__':main()
