"""Use the verified stock clock startup before UFS; preserve Wi-Fi/SSH payload."""
import hashlib,json,secrets,struct
from pathlib import Path
from image_formats import read_boot_v4,read_newc,require
from ramdisk_codec import decompress
from network_userspace import put
from prepare_busybox_diagnostics import pack
P=Path(__file__).resolve().parent;F=P/'artifacts/busybox-wifi-ssh-twostage-v5';OUT=P/'artifacts/busybox-wifi-ssh-twostage-v6'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def main():
    require(not OUT.exists(),'Preserve prior images')
    original=(F/'nord3-busybox-candidate.img').read_bytes();require(sha(original)=='856e9f39f283593777608fc838afb66a130398732585035dc0c61bfd1925c3af','Wi-Fi reference changed')
    boot=read_boot_v4(original);entries=read_newc(decompress(boot['ramdisk']));init=entries['init']['data'];guard=(P/'stock-clock-helper-guard.sh').read_bytes()
    anchor=b'lynx_load_checkpoint_modules() {\n';require(init.count(anchor)==1,'Loader boundary changed');init=init.replace(anchor,guard+anchor)
    anchor=b'        log "CHECKPOINT_MODULE_BEGIN $module"\n';require(init.count(anchor)==1,'Module boundary changed')
    addition=b'''        if [ "$module" = ufs-mediatek-mod.ko ]; then
            lynx_stock_clock_helper_load
            clock_startup_status=$?
            if [ "$clock_startup_status" != 0 ]; then
                lynx_diag_emit 516 "$clock_startup_status" || true
                log "STOCK_CLOCK_HELPER_FAILED_BEFORE_UFS status=$clock_startup_status"
                return 1
            fi
        fi
'''
    init=init.replace(anchor,anchor+addition);put(entries,'init',init)
    base=entries['etc/lynx/bootstrap-base-modules.load']['data'].decode().splitlines();require(len(base)==38 and base[-4:]==['phy-mtk-xsphy.ko','tcpc_mt6375.ko','extcon-mtk-usb.ko','xhci-mtk-hcd.ko'],'USB suffix changed')
    base=base[:34];put(entries,'etc/lynx/bootstrap-base-modules.load',('\n'.join(base)+'\n').encode(),0o100644)
    token=secrets.token_hex(16);put(entries,'etc/lynx/session-token',(token+'\n').encode(),0o100644)
    book=json.loads(entries['etc/lynx/diag-codebook.json']['data']);book['516']='stock clock helper: load1, returned2, bound/counters3, refused or failed10..13';put(entries,'etc/lynx/diag-codebook.json',(json.dumps(book,indent=2)+'\n').encode(),0o100644)
    rd=pack(entries);header=bytearray(original[:1584]);struct.pack_into('<I',header,12,len(rd));align=lambda n:(n+4095)//4096*4096
    loaded=bytes(header).ljust(4096,b'\0')+boot['kernel'].ljust(align(len(boot['kernel'])),b'\0')+rd.ljust(align(len(rd)),b'\0');coverage=struct.unpack('!4sIIQQQ28x',original[-64:])[3];require(len(loaded)<=coverage,'Metadata overlap');image=loaded.ljust(coverage,b'\0')+original[coverage:]
    OUT.mkdir(mode=0o700)
    for name,raw in [('nord3-busybox-candidate.img',image),('init-source',init),('supplement.cpio.gz',(F/'supplement.cpio.gz').read_bytes()),('diag-hooks.sh',(F/'diag-hooks.sh').read_bytes())]:
        path=OUT/name;path.write_bytes(raw);path.chmod(0o600)
    report=json.loads((F/'build-validation.json').read_text());report.update(candidate=str(OUT/'nord3-busybox-candidate.img'),candidate_sha256=sha(image),init_sha256=sha(init),ramdisk_bytes=len(rd),session_token=token,diagnostic_codebook=book,base_modules=base,stock_clock_guard_sha256=sha(guard),stock_clock_helper_sha256='4b62b692837be57cc9aab66136dec5d772840c8f572c37c20c59bda979216823',clock_helper_before_main_ufs=True,usb_supplier_suffix_loaded=False,phone_contacted=False,flash_eligible=False)
    (OUT/'build-validation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(candidate_sha256=sha(image),ramdisk_bytes=len(rd),session_token=token),indent=2))
if __name__=='__main__':main()
