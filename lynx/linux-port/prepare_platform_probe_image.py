"""Build a stock-kernel diagnostic for the checks before UFS driver probing."""
import hashlib
import json
import secrets
import struct
from pathlib import Path
from image_formats import read_boot_v4, read_newc, require
from ramdisk_codec import decompress
from network_userspace import put
from prepare_busybox_diagnostics import pack

P=Path(__file__).resolve().parent
F=P/'artifacts/busybox-core-probe-v1'
OUT=P/'artifacts/busybox-platform-probe-v1'


def main():
    require(not OUT.exists(),'Preserve previous diagnostic')
    data=(F/'nord3-busybox-candidate.img').read_bytes()
    require(hashlib.sha256(data).hexdigest()=='dbc47af2604563013d2e7591c81b788551938d4467aeedad131370c4ae4eb94f','Reference changed')
    boot=read_boot_v4(data); entries=read_newc(decompress(boot['ramdisk']))
    old=(F/'trace-runtime.sh').read_bytes()
    collector=(P/'lynx-driver-trace-platform-v2.sh').read_bytes()
    classifier=(P/'lynx-classify-platform-trace.awk').read_bytes()
    runtime=collector+old[old.index(b'# Coarse timing channel'):]
    start=runtime.index(b'        probe_code=1\n')
    end=runtime.index(b"        printf '%s %s\\n'",start)
    runtime=runtime[:start]+b'''        probe_code=1
        if [ "$trace_ready" = 1 ] && lynx_driver_trace_capture; then
            trace_expected_pid=$($BB cat /run/lynx/trace-health-pid)
            trace_registration_failed=0
            if $BB grep -Eq 'Failed to re-register probe mtk_probe_(enter|return) on ufs_mediatek_mod:' /run/lynx/kernel-dmesg.log; then
                trace_registration_failed=1
            fi
            if $BB awk -v expected_pid="$trace_expected_pid" -v registration_failed="$trace_registration_failed" -f /etc/lynx/classify-driver-trace.awk /run/lynx/driver-trace.log > /run/lynx/driver-trace-result; then
                if IFS=' ' read -r probe_code trace_match_ret trace_dma_ret trace_platform_ret trace_health_count < /run/lynx/driver-trace-result; then
                    case "$probe_code" in 1|2|3|4|5|6|7) ;; *) probe_code=1 ;; esac
                    log "PLATFORM_CLASSIFIED code=$probe_code match=$trace_match_ret dma=$trace_dma_ret platform=$trace_platform_ret health=$trace_health_count"
                fi
            fi
        fi
'''+runtime[end:]
    init=entries['init']['data']; require(init.count(old)==1,'Runtime boundary changed')
    init=init.replace(old,runtime,1); put(entries,'init',init)
    put(entries,'etc/lynx/classify-driver-trace.awk',classifier,0o100644)
    token=secrets.token_hex(16); put(entries,'etc/lynx/session-token',(token+'\n').encode(),0o100644)
    ramdisk=pack(entries); header=bytearray(data[:1584]); struct.pack_into('<I',header,12,len(ramdisk))
    align=lambda n:(n+4095)//4096*4096
    loaded=bytes(header).ljust(4096,b'\0')+boot['kernel'].ljust(align(len(boot['kernel'])),b'\0')+ramdisk.ljust(align(len(ramdisk)),b'\0')
    coverage=struct.unpack('!4sIIQQQ28x',data[-64:])[3]
    require(len(loaded)<=coverage,'Original loaded area exceeded')
    image=loaded.ljust(coverage,b'\0')+data[coverage:]
    require(len(image)==len(data) and image[coverage:]==data[coverage:],'Supplement/metadata changed')
    OUT.mkdir(mode=0o700)
    for name,raw in [('nord3-busybox-candidate.img',image),('init-source',init),('trace-runtime.sh',runtime),('collector-source.sh',collector)]:
        path=OUT/name; path.write_bytes(raw); path.chmod(0o600)
    report=json.loads((F/'build-validation.json').read_text())
    report.update(candidate=str(OUT/'nord3-busybox-candidate.img'),candidate_sha256=hashlib.sha256(image).hexdigest(),
                  init_sha256=hashlib.sha256(init).hexdigest(),ramdisk_bytes=len(ramdisk),session_token=token,
                  runtime_sha256=hashlib.sha256(runtime).hexdigest(),trace_source_sha256=hashlib.sha256(collector).hexdigest(),
                  classifier_sha256=hashlib.sha256(classifier).hexdigest(),phone_contacted=False,flash_eligible=False,
                  result_codes={'1':'trace health/capture/correlation unavailable',
                                '2':'last UFS match with expected driver returned zero or negative',
                                '3':'last matched UFS DMA configure returned nonzero',
                                '4':'last matched UFS platform probe wrapper returned nonzero',
                                '5':'healthy tracing but no completed expected UFS driver match recorded',
                                '6':'expected UFS driver matched; no completed platform probe wrapper recorded',
                                '7':'last matched UFS platform probe wrapper returned zero',
                                '8':'bootstrap worker exceeded 180 second deadline'})
    (OUT/'build-validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ['candidate_sha256','ramdisk_bytes','flash_eligible']},indent=2))


if __name__=='__main__':main()
