"""Strict traced-probe derivative checks; never contact the handset."""
import hashlib,json,stat,struct,subprocess,sys
from pathlib import Path
R=Path(__file__).resolve().parent.parent;P=R/'linux-port';sys.path.insert(0,str(P))
from image_formats import read_boot_v4,read_newc,require
from ramdisk_codec import decompress
SHA='30a2757ef742a859a24d577b35bf33111c3ed3cc5d43baa4199cf0d889f363ff'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def matching_receipt(pattern,expected):
    receipts=[]
    for path in sorted((P/'artifacts').glob(pattern)):
        row=json.loads(path.read_text())
        if row.get('passed') and all(row.get(k)==v for k,v in expected.items()):receipts.append(path)
    require(receipts,'Passing matching receipt missing: '+pattern);return str(receipts[-1])
def main():
    parent=subprocess.run(['python3',str(R/'tools/validate_ufs_registration_image.py')],capture_output=True,text=True,timeout=60)
    require(parent.returncode==0,'Parent validation failed: '+parent.stdout+parent.stderr)
    F=P/'artifacts/busybox-ufs-trace-probe-v1';REF=P/'artifacts/busybox-ufs-registration-only-v1'
    image=(F/'nord3-busybox-candidate.img').read_bytes();reference=(REF/'nord3-busybox-candidate.img').read_bytes()
    require(sha(image)==SHA and len(image)==67108864,'Pinned image changed')
    require(stat.S_IMODE(F.stat().st_mode)==0o700 and stat.S_IMODE((F/'nord3-busybox-candidate.img').stat().st_mode)==0o600,'Private permissions changed')
    boot,prior=read_boot_v4(image),read_boot_v4(reference);require(boot['kernel']==prior['kernel'] and boot['cmdline']==prior['cmdline']+' tp_printk','Kernel or cmdline changed')
    require(image[:12]==reference[:12] and image[16:44]==reference[16:44] and image[1580:4096]==reference[1580:4096],'Header geometry changed')
    current,old=read_newc(decompress(boot['ramdisk'])),read_newc(decompress(prior['ramdisk']))
    require(set(current)==set(old) and {n for n in old if current[n]!=old[n]}=={'init','etc/lynx/session-token','etc/lynx/diag-codebook.json'},'Unrelated archive changes')
    guard=(P/'ufs-registration-guard.sh').read_bytes();setup=(P/'ufs-persistent-trace-setup.sh').read_bytes();runtime=(P/'lynx-ufs-trace-probe-runtime.sh').read_bytes()
    suffix=guard+(P/'lynx-ufs-registration-runtime.sh').read_bytes()+b'\nlynx_ufs_registration\nstop\n'
    require(old['init']['data'].endswith(suffix),'Frozen parent boundary changed')
    expected=old['init']['data'][:-len(suffix)]+guard+setup+runtime+b'\nlynx_ufs_registration\nstop\n'
    require(current['init']['data']==expected==(F/'init-source').read_bytes(),'Executable source differs')
    require(runtime.count(b'/bin/boot-proof-reboot\n')==1 and b'/proc/sysrq-trigger' not in runtime,'One-normal-reset policy changed')
    coverage=struct.unpack('!4sIIQQQ28x',reference[-64:])[3];require(image[coverage:]==reference[coverage:],'Stock metadata/footer/payload changed')
    require(4096+((len(boot['kernel'])+4095)//4096)*4096+((len(boot['ramdisk'])+4095)//4096)*4096<=coverage,'Loaded area overlaps metadata')
    manifest=json.loads((F/'build-validation.json').read_text());require(manifest['runtime_sha256']==sha(runtime) and manifest['trace_setup_sha256']==sha(setup),'Source hashes changed')
    require(manifest['session_token']==current['etc/lynx/session-token']['data'].decode().strip(),'Session token differs')
    book=json.loads(old['etc/lynx/diag-codebook.json']['data']);book['515']='trace ready16, before controlled probe17, probe returned18';require(json.loads(current['etc/lynx/diag-codebook.json']['data'])==book,'Stage map changed')
    trace=matching_receipt('emulated-native-ufs-trace-registration-*/result.json',dict(setup_source_sha256=sha(setup),kernel_sha256=sha(boot['kernel'])))
    printk=matching_receipt('emulated-native-trace-printk-*/result.json',dict(kernel_sha256=sha(boot['kernel'])))
    controls={}
    for pattern,digest in [('ufs-controlled-probe-*',sha(setup)),('ufs-trace-probe-control-*',sha(runtime))]:
        paths=[p for p in sorted((R/'tools/test-artifacts').glob(pattern+'/result.json')) if json.loads(p.read_text()).get('passed') and json.loads(p.read_text()).get('source_sha256')==digest]
        require(paths,'Matching control test missing: '+pattern);controls[pattern]=str(paths[-1])
    guards=sorted((P/'artifacts').glob('emulated-ufs-trace-probe-guard-*/result.json'));require(guards,'Exact guard missing');g=json.loads(guards[-1].read_text());require(g['candidate_sha256']==SHA and g['module_checkpoint_failure_guard_observed'] and not g['kernel_reboot_command_observed'],'Reset guard failed')
    require(manifest['target_delays_seconds']=={str(i):120+5*i for i in range(10)} and manifest['worker_sample_seconds']==90 and manifest['observation_seconds']==240 and manifest['timing_match_tolerance_seconds']==2,'Timing profile differs')
    timing=json.loads((P/'docs/ufs-trace-probe-timing-test.json').read_text());require(timing['passed'],'Timing tests failed')
    model=R/'tools/avb-host/avb-boot-model';mref=json.loads((P/'docs/avb-boot-model-results.json').read_text());require(sha(model.read_bytes())==mref['binary_sha256'],'Boot model changed')
    for unlocked in ['0','1']:
        result=subprocess.run([str(model),str(P/'artifacts/stock-cph2493-August-eu-ota'),str(F/'nord3-busybox-candidate.img'),'0',unlocked],capture_output=True,text=True,timeout=30)
        require(result.returncode==0 and json.loads(result.stdout)['slot_data_returned']==(unlocked=='1'),'Boot policy changed')
    out=P/'docs/ufs-trace-probe-validation.json';report=dict(passed=True,candidate_sha256=SHA,trace_receipt=trace,printk_receipt=printk,controls=controls,guard_receipt=str(guards[-1]),phone_contacted=False,limits='Physical probe completion/reset/log persistence not guaranteed. Kernel/modules and recovery bytes preserved; only standard RAM trace/override/probe controls requested.')
    out.write_text(json.dumps(report,indent=2)+'\n');print(out)
if __name__=='__main__':main()
