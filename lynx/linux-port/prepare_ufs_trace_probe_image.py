"""Preserve prior images; prepare a controlled, logged stock UFS probe."""
import hashlib,json,secrets,struct
from pathlib import Path
from image_formats import read_boot_v4,read_newc,require
from ramdisk_codec import decompress
from network_userspace import put
from prepare_busybox_diagnostics import pack
P=Path(__file__).resolve().parent;F=P/'artifacts/busybox-ufs-registration-only-v1';OUT=P/'artifacts/busybox-ufs-trace-probe-v1'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def main():
    require(not OUT.exists(),'Preserve existing candidates')
    original=(F/'nord3-busybox-candidate.img').read_bytes();require(sha(original)=='034177798aed0cb0210e51eaf563eefc055abe6fcdbde3d272f89003b1880a56','Reference changed')
    boot=read_boot_v4(original);entries=read_newc(decompress(boot['ramdisk']))
    prior=(P/'lynx-ufs-registration-runtime.sh').read_bytes();guard=(P/'ufs-registration-guard.sh').read_bytes();setup=(P/'ufs-persistent-trace-setup.sh').read_bytes()
    old=b'''            lynx_ufs_registration_state 0 || exit 1
            log 'UFS_REGISTRATION_INSERTION_RETURNED; HARDWARE_PROBE_BLOCKED'
'''
    new=b'''            lynx_ufs_guarded_probe
            ufs_probe_status=$?
            case "$ufs_probe_status" in 0|6|7|8|9) ;; *) ufs_probe_status=5 ;; esac
            lynx_ufs_registration_state "$ufs_probe_status" || exit 1
            log "UFS_TRACED_WORKER_FINISHED status=$ufs_probe_status"
'''
    require(prior.count(old)==1,'Probe insertion boundary changed')
    runtime=prior.replace(old,new).replace(b'in 0|1|2|3|4)',b'in 0|1|2|3|4|5|6|7|8|9)')
    path=P/'lynx-ufs-trace-probe-runtime.sh';require(not path.exists(),'Preserve runtime');path.write_bytes(runtime)
    suffix=guard+prior+b'\nlynx_ufs_registration\nstop\n';require(entries['init']['data'].endswith(suffix),'Frozen init boundary changed')
    init=entries['init']['data'][:-len(suffix)]+guard+setup+runtime+b'\nlynx_ufs_registration\nstop\n';put(entries,'init',init)
    token=secrets.token_hex(16);put(entries,'etc/lynx/session-token',(token+'\n').encode(),0o100644)
    book=json.loads(entries['etc/lynx/diag-codebook.json']['data']);book['515']='trace ready16, before controlled probe17, probe returned18';put(entries,'etc/lynx/diag-codebook.json',(json.dumps(book,indent=2)+'\n').encode(),0o100644)
    rd=pack(entries);header=bytearray(original[:1584]);struct.pack_into('<I',header,12,len(rd));cmdline=(boot['cmdline']+' tp_printk').encode();require(len(cmdline)<1536,'Kernel arguments too long');header[44:1580]=cmdline.ljust(1536,b'\0')
    align=lambda n:(n+4095)//4096*4096
    loaded=bytes(header).ljust(4096,b'\0')+boot['kernel'].ljust(align(len(boot['kernel'])),b'\0')+rd.ljust(align(len(rd)),b'\0');coverage=struct.unpack('!4sIIQQQ28x',original[-64:])[3];require(len(loaded)<=coverage,'Metadata overlap')
    image=loaded.ljust(coverage,b'\0')+original[coverage:];OUT.mkdir(mode=0o700)
    for name,raw in [('nord3-busybox-candidate.img',image),('init-source',init),('runtime-source',runtime),('trace-setup-source',setup)]:
        path=OUT/name;path.write_bytes(raw);path.chmod(0o600)
    report=json.loads((F/'build-validation.json').read_text());report.update(candidate_sha256=sha(image),reference_sha256=sha(original),runtime_sha256=sha(runtime),trace_setup_sha256=sha(setup),init_sha256=sha(init),ramdisk_bytes=len(rd),session_token=token,controlled_probe_enabled=True,tp_printk_enabled=True,target_delays_seconds={str(i):120+5*i for i in range(10)},result_codes={'0':'controlled probe returned with ufshcd-mtk bound; block access untested','1':'guard refused','2':'main UFS insertion failed','3':'worker still pending','4':'prefix insertion failed','5':'missing or malformed outcome','6':'trace setup failed; probe not requested','7':'controlled probe write failed','8':'probe returned without expected driver binding','9':'override clear or probe prerequisite refused'},trace_event_symbols={str(i):name for i,name in enumerate(['ufs_mtk_probe','ufs_mtk_init','ufs_mtk_setup_clocks','ufs_mtk_mphy_power_on','ufs_mtk_setup_ref_clk','ufs_mtk_hce_enable_notify','platform_drv_probe','dev_pm_domain_attach','genpd_dev_pm_attach'],1)})
    (OUT/'build-validation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(candidate_sha256=sha(image),ramdisk_bytes=len(rd),session_token=token),indent=2))
if __name__=='__main__':main()
