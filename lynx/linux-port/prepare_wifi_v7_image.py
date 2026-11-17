"""Retain the physically successful guarded UFS startup in the Wi-Fi image."""
import hashlib,json,secrets,struct
from pathlib import Path
from image_formats import read_boot_v4,read_newc,require
from ramdisk_codec import decompress
from network_userspace import put
from prepare_busybox_diagnostics import pack
P=Path(__file__).resolve().parent;F=P/'artifacts/busybox-wifi-ssh-twostage-v6';OUT=P/'artifacts/busybox-wifi-ssh-twostage-v7'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def main():
    require(not OUT.exists(),'Preserve prior images')
    original=(F/'nord3-busybox-candidate.img').read_bytes();require(sha(original)=='eb50fc9027c52453b4cc43e872900dff2c22037d0945a5d74490d854dd1c3dab','Reference changed')
    boot=read_boot_v4(original);entries=read_newc(decompress(boot['ramdisk']));init=entries['init']['data'];guard=(P/'ufs-registration-guard.sh').read_bytes();trace=(P/'ufs-refclk-persistent-trace-v2-setup.sh').read_bytes()
    anchor=b'lynx_load_checkpoint_modules() {\n';require(init.count(anchor)==1,'Loader boundary changed');init=init.replace(anchor,guard+trace+anchor)
    anchor=b'        if [ "$module" = ufs-mediatek-mod.ko ]; then\n';require(init.count(anchor)==1,'UFS guard boundary changed');init=init.replace(anchor,anchor+b'            lynx_ufs_registration_guard || return 1\n')
    anchor=b'        log "CHECKPOINT_MODULE_OK $module"\n';require(init.count(anchor)==1,'Postload boundary changed');init=init.replace(anchor,b'''        if [ "$module" = ufs-mediatek-mod.ko ]; then
            lynx_ufs_guarded_probe || return 1
        fi
'''+anchor);put(entries,'init',init)
    token=secrets.token_hex(16);put(entries,'etc/lynx/session-token',(token+'\n').encode(),0o100644)
    book=json.loads(entries['etc/lynx/diag-codebook.json']['data']);book['515']='trace ready16, before controlled probe17, probe returned18';put(entries,'etc/lynx/diag-codebook.json',(json.dumps(book,indent=2)+'\n').encode(),0o100644)
    rd=pack(entries);header=bytearray(original[:1584]);struct.pack_into('<I',header,12,len(rd));cmd=(boot['cmdline']+' initcall_debug tp_printk').encode();require(len(cmd)<1536,'Command line too long');header[44:1580]=cmd.ljust(1536,b'\0');align=lambda n:(n+4095)//4096*4096
    loaded=bytes(header).ljust(4096,b'\0')+boot['kernel'].ljust(align(len(boot['kernel'])),b'\0')+rd.ljust(align(len(rd)),b'\0');coverage=struct.unpack('!4sIIQQQ28x',original[-64:])[3];require(len(loaded)<=coverage,'Metadata overlap');image=loaded.ljust(coverage,b'\0')+original[coverage:]
    OUT.mkdir(mode=0o700)
    for name,raw in [('nord3-busybox-candidate.img',image),('init-source',init),('supplement.cpio.gz',(F/'supplement.cpio.gz').read_bytes()),('diag-hooks.sh',(F/'diag-hooks.sh').read_bytes())]:
        path=OUT/name;path.write_bytes(raw);path.chmod(0o600)
    report=json.loads((F/'build-validation.json').read_text());report.update(candidate=str(OUT/'nord3-busybox-candidate.img'),candidate_sha256=sha(image),init_sha256=sha(init),ramdisk_bytes=len(rd),session_token=token,diagnostic_codebook=book,guarded_ufs_probe=True,ufs_guard_sha256=sha(guard),refclk_trace_sha256=sha(trace),successful_ufs_trial_receipt=str(P.parent/'logs/boot-a-stock-clock-helper-probe-trial-1792003167463063951.json'))
    (OUT/'build-validation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(candidate_sha256=sha(image),ramdisk_bytes=len(rd),session_token=token),indent=2))
if __name__=='__main__':main()
