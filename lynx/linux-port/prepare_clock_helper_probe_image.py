"""One stock clock-startup addition to the preserved, guarded UFS diagnostic."""
import hashlib,json,secrets,struct
from pathlib import Path
from image_formats import read_boot_v4,read_newc,require
from ramdisk_codec import decompress
from network_userspace import put
from prepare_busybox_diagnostics import pack
P=Path(__file__).resolve().parent;F=P/'artifacts/busybox-refclk-trace-probe-v2';OUT=P/'artifacts/busybox-stock-clock-helper-probe-v1'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def main():
    require(not OUT.exists(),'Preserve prior candidates')
    original=(F/'nord3-busybox-candidate.img').read_bytes();require(sha(original)=='b4a505426c91b3a0c151b977ddcfbfddeabcca612a59959408230c19d317aea1','Reference changed')
    boot=read_boot_v4(original);entries=read_newc(decompress(boot['ramdisk']))
    guard=(P/'stock-clock-helper-guard.sh').read_bytes();old=(P/'lynx-ufs-trace-probe-runtime.sh').read_bytes()
    boundary=b'        log \'UFS_REGISTRATION_STOCK_MODULE_BEGIN\'\n';require(old.count(boundary)==1,'Worker boundary changed')
    addition=b'''        lynx_stock_clock_helper_load
        clock_helper_status=$?
        if [ "$clock_helper_status" != 0 ]; then
            case "$clock_helper_status" in 10|11|12|13) ;; *) clock_helper_status=5 ;; esac
            lynx_ufs_registration_state "$clock_helper_status"
            exit 1
        fi
'''
    runtime=old.replace(boundary,addition+boundary).replace(b'in 0|1|2|3|4|5|6|7|8|9)',b'in 0|1|2|3|4|5|6|7|8|9|10|11|12|13)')
    runtime_path=P/'lynx-stock-clock-helper-probe-runtime.sh';require(not runtime_path.exists(),'Preserve runtime');runtime_path.write_bytes(runtime)
    require(entries['init']['data'].count(old)==1,'Frozen runtime boundary changed');init=entries['init']['data'].replace(old,guard+runtime);put(entries,'init',init)
    token=secrets.token_hex(16);put(entries,'etc/lynx/session-token',(token+'\n').encode(),0o100644)
    book=json.loads(entries['etc/lynx/diag-codebook.json']['data']);book['516']='stock clock helper: before load1, load returned2, bound and bus counters enabled3';put(entries,'etc/lynx/diag-codebook.json',(json.dumps(book,indent=2)+'\n').encode(),0o100644)
    vendor=read_newc(decompress((P/'artifacts/stock-cph2493-August-eu-ota/unpacked-vendor-boot/vendor_ramdisk00').read_bytes()));merged={**vendor,**entries};helper=merged['lib/modules/clk-bringup.ko']['data'];require(sha(helper)=='4b62b692837be57cc9aab66136dec5d772840c8f572c37c20c59bda979216823','Stock vendor helper changed')
    rd=pack(entries);header=bytearray(original[:1584]);struct.pack_into('<I',header,12,len(rd));align=lambda n:(n+4095)//4096*4096
    loaded=bytes(header).ljust(4096,b'\0')+boot['kernel'].ljust(align(len(boot['kernel'])),b'\0')+rd.ljust(align(len(rd)),b'\0');coverage=struct.unpack('!4sIIQQQ28x',original[-64:])[3];require(len(loaded)<=coverage,'Metadata overlap');image=loaded.ljust(coverage,b'\0')+original[coverage:]
    OUT.mkdir(mode=0o700)
    for name,raw in [('nord3-busybox-candidate.img',image),('init-source',init),('runtime-source',runtime),('clock-guard-source',guard)]:
        path=OUT/name;path.write_bytes(raw);path.chmod(0o600)
    report=json.loads((F/'build-validation.json').read_text());codes=dict(report['result_codes']);codes.update({'10':'stock clock helper guard refused; no UFS probe requested','11':'stock clock helper insertion failed; no UFS probe requested','12':'stock clock helper not bound; no UFS probe requested','13':'bus clock framework counts unavailable or zero; no UFS probe requested'})
    report.update(candidate_sha256=sha(image),reference_sha256=sha(original),runtime_sha256=sha(runtime),clock_guard_sha256=sha(guard),init_sha256=sha(init),ramdisk_bytes=len(rd),session_token=token,stock_clock_helper_sha256=sha(helper),clock_helper_supplied_by_stock_vendor_ramdisk=True,diagnostic_codebook=book,result_codes=codes,target_delays_seconds={str(i):120+5*i for i in range(14)})
    (OUT/'build-validation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(candidate_sha256=sha(image),ramdisk_bytes=len(rd),session_token=token),indent=2))
if __name__=='__main__':main()
