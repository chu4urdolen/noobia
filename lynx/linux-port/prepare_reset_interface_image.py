"""Isolate the reviewed clock prefix; retain exact prior images and stock undo."""
import argparse,hashlib,json,secrets,struct
from pathlib import Path
from image_formats import read_boot_v4,read_newc,require
from ramdisk_codec import decompress
from network_userspace import put
from prepare_busybox_diagnostics import pack
P=Path(__file__).resolve().parent;F=P/'artifacts/busybox-wifi-ssh-twostage-v5'
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--count',type=int,choices=[0],required=True);args=parser.parse_args()
    OUT=P/'artifacts'/('busybox-reset-interface-v1')
    require(not OUT.exists(),'Preserve prior candidates')
    original=(F/'nord3-busybox-candidate.img').read_bytes();require(hashlib.sha256(original).hexdigest()=='856e9f39f283593777608fc838afb66a130398732585035dc0c61bfd1925c3af','Reference changed')
    boot=read_boot_v4(original);entries=read_newc(decompress(boot['ramdisk']));old_init=entries['init']['data']
    marker=b"\nlog 'WIFI_TWO_STAGE_BOOTSTRAP_BEGIN'\n";require(old_init.count(marker)==1,'Main boundary changed')
    runtime=(P/'lynx-reset-interface-runtime.sh').read_bytes()
    init=old_init.split(marker)[0]+runtime+b'\nlynx_module_progress\nstop\n';put(entries,'init',init)
    modules=entries['etc/lynx/bootstrap-base-modules.load']['data'].decode().splitlines();prefix=modules[:args.count]
    require(args.count==0 or prefix[-1].startswith('clk-mt6983-'),'Unexpected prefix')
    put(entries,'etc/lynx/progress-count',(str(args.count)+'\n').encode(),0o100644)
    put(entries,'etc/lynx/progress-modules.load',('\n'.join(prefix)+'\n').encode(),0o100644)
    token=secrets.token_hex(16);put(entries,'etc/lynx/session-token',(token+'\n').encode(),0o100644)
    codebook=json.loads(entries['etc/lynx/diag-codebook.json']['data']);codebook['512']='module progress field';put(entries,'etc/lynx/diag-codebook.json',(json.dumps(codebook,indent=2)+'\n').encode(),0o100644)
    rd=pack(entries);header=bytearray(original[:1584]);struct.pack_into('<I',header,12,len(rd));cmdline=(boot['cmdline']+' initcall_debug').encode();require(len(cmdline)<1536,'Commandline size');header[44:1580]=cmdline.ljust(1536,b'\0');align=lambda n:(n+4095)//4096*4096
    loaded=bytes(header).ljust(4096,b'\0')+boot['kernel'].ljust(align(len(boot['kernel'])),b'\0')+rd.ljust(align(len(rd)),b'\0')
    coverage=struct.unpack('!4sIIQQQ28x',original[-64:])[3];require(len(loaded)<=coverage,'Metadata overlap')
    image=loaded.ljust(coverage,b'\0')+original[coverage:];OUT.mkdir(mode=0o700)
    for name,raw in [('nord3-busybox-candidate.img',image),('init-source',init),('progress-runtime.sh',runtime)]:
        path=OUT/name;path.write_bytes(raw);path.chmod(0o600)
    codes={str(i):'reserved; do not interpret' for i in range(128)}
    for i,name in enumerate(prefix,1):
        codes[str(i)]='insertion still pending at sample: '+name
        codes[str(i+40)]='last insertion completed before sampling: '+name
        codes[str(i+80)]='insertion returned failure: '+name
    codes.update({'0':'SysRq help write accepted; emergency reset not executed','1':'SysRq help write rejected','2':'SysRq interface absent','3':'SysRq help request pending at sample','125':'malformed progress record','127':'worker progress unavailable'})
    report=json.loads((F/'build-validation.json').read_text());report.update(diagnostic_codebook=codebook,candidate=str(OUT/'nord3-busybox-candidate.img'),candidate_sha256=hashlib.sha256(image).hexdigest(),init_sha256=hashlib.sha256(init).hexdigest(),ramdisk_bytes=len(rd),session_token=token,module_progress_prefix=prefix,module_progress_count=args.count,initcall_debug_enabled=True,calibration_only=False,reset_interface_check=True,result_codes=codes,target_delays_seconds={str(n):120+2*n for n in range(128)},baseline_reference_seconds=21.9,timing_match_tolerance_seconds=0.8,observation_seconds=420,worker_sample_seconds=90,runtime_sha256=hashlib.sha256(runtime).hexdigest(),phone_contacted=False,flash_eligible=False)
    (OUT/'build-validation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:report[k] for k in ['candidate_sha256','ramdisk_bytes','flash_eligible']},indent=2))
if __name__=='__main__':main()
