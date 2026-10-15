"""Replace trace definitions only; keep driver/probe/reset behavior unchanged."""
import hashlib,json,secrets,struct
from pathlib import Path
from image_formats import read_boot_v4,read_newc,require
from ramdisk_codec import decompress
from network_userspace import put
from prepare_busybox_diagnostics import pack
P=Path(__file__).resolve().parent;F=P/'artifacts/busybox-ufs-trace-probe-v1';OUT=P/'artifacts/busybox-refclk-trace-probe-v2'
LABELS=['ufs_mtk_setup_ref_clk entry','before firmware call (+0x88)','after firmware call (+0x8c)','before request register store (+0xa0)','after request register store (+0xa4)','before acknowledgement register read (+0xf0)','after acknowledgement register read (+0xf8)','ufs_mtk_setup_ref_clk returned','ufs_mtk_boost_crypt entry']
def sha(raw):return hashlib.sha256(raw).hexdigest()
def main():
    require(not OUT.exists(),'Preserve earlier images')
    original=(F/'nord3-busybox-candidate.img').read_bytes();require(sha(original)=='30a2757ef742a859a24d577b35bf33111c3ed3cc5d43baa4199cf0d889f363ff','Traced reference changed')
    boot=read_boot_v4(original);entries=read_newc(decompress(boot['ramdisk']))
    old_setup=(P/'ufs-persistent-trace-setup.sh').read_bytes();setup=(P/'ufs-refclk-persistent-trace-v2-setup.sh').read_bytes();require(entries['init']['data'].count(old_setup)==1,'Trace boundary changed')
    require(old_setup.split(b'lynx_ufs_guarded_probe()')[1]==setup.split(b'lynx_ufs_guarded_probe()')[1],'Probe behavior changed')
    init=entries['init']['data'].replace(old_setup,setup);put(entries,'init',init)
    token=secrets.token_hex(16);put(entries,'etc/lynx/session-token',(token+'\n').encode(),0o100644)
    rd=pack(entries);header=bytearray(original[:1584]);struct.pack_into('<I',header,12,len(rd));align=lambda n:(n+4095)//4096*4096
    loaded=bytes(header).ljust(4096,b'\0')+boot['kernel'].ljust(align(len(boot['kernel'])),b'\0')+rd.ljust(align(len(rd)),b'\0');coverage=struct.unpack('!4sIIQQQ28x',original[-64:])[3];require(len(loaded)<=coverage,'Metadata overlap');image=loaded.ljust(coverage,b'\0')+original[coverage:]
    OUT.mkdir(mode=0o700)
    for name,raw in [('nord3-busybox-candidate.img',image),('init-source',init),('trace-setup-source',setup)]:
        path=OUT/name;path.write_bytes(raw);path.chmod(0o600)
    report=json.loads((F/'build-validation.json').read_text());report.update(candidate_sha256=sha(image),reference_sha256=sha(original),trace_setup_sha256=sha(setup),init_sha256=sha(init),ramdisk_bytes=len(rd),session_token=token,refclk_offset_trace=True,trace_event_symbols={str(i):name for i,name in enumerate(LABELS,1)},trace_events_all_ufs_specific=True)
    (OUT/'build-validation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(candidate_sha256=sha(image),ramdisk_bytes=len(rd),session_token=token),indent=2))
if __name__=='__main__':main()
