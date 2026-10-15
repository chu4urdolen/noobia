"""Validate a trace-only derivative of the established controlled UFS probe."""
import hashlib,json,stat,struct,subprocess,sys
from pathlib import Path
R=Path(__file__).resolve().parent.parent;P=R/'linux-port';sys.path.insert(0,str(P))
from image_formats import read_boot_v4,read_newc,require
from ramdisk_codec import decompress
SHA='b4a505426c91b3a0c151b977ddcfbfddeabcca612a59959408230c19d317aea1'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def main():
    check=subprocess.run(['python3',str(R/'tools/validate_ufs_trace_probe_image.py')],capture_output=True,text=True,timeout=60);require(check.returncode==0,'Parent validation failed: '+check.stdout+check.stderr)
    F=P/'artifacts/busybox-refclk-trace-probe-v2';REF=P/'artifacts/busybox-ufs-trace-probe-v1'
    image=(F/'nord3-busybox-candidate.img').read_bytes();reference=(REF/'nord3-busybox-candidate.img').read_bytes();require(sha(image)==SHA and len(image)==67108864,'Image changed')
    require(stat.S_IMODE(F.stat().st_mode)==0o700 and stat.S_IMODE((F/'nord3-busybox-candidate.img').stat().st_mode)==0o600,'Private permissions changed')
    boot,prior=read_boot_v4(image),read_boot_v4(reference);require(boot['kernel']==prior['kernel'] and boot['cmdline']==prior['cmdline'],'Kernel/cmdline changed')
    require(image[:12]==reference[:12] and image[16:4096]==reference[16:4096],'Header geometry changed')
    entries,old=read_newc(decompress(boot['ramdisk'])),read_newc(decompress(prior['ramdisk']));require(set(entries)==set(old) and {n for n in old if entries[n]!=old[n]}=={'init','etc/lynx/session-token'},'Unrelated archive changes')
    setup=(P/'ufs-refclk-persistent-trace-v2-setup.sh').read_bytes();old_setup=(P/'ufs-persistent-trace-setup.sh').read_bytes();require(old['init']['data'].count(old_setup)==1,'Parent trace boundary changed')
    require(entries['init']['data']==old['init']['data'].replace(old_setup,setup)==(F/'init-source').read_bytes(),'Executable source differs')
    require(setup.split(b'lynx_ufs_guarded_probe()')[1]==old_setup.split(b'lynx_ufs_guarded_probe()')[1],'Probe behavior changed')
    coverage=struct.unpack('!4sIIQQQ28x',reference[-64:])[3];require(image[coverage:]==reference[coverage:],'Stock metadata/footer/payload changed');require(4096+((len(boot['kernel'])+4095)//4096)*4096+((len(boot['ramdisk'])+4095)//4096)*4096<=coverage,'Metadata overlap')
    manifest=json.loads((F/'build-validation.json').read_text());prior_manifest=json.loads((REF/'build-validation.json').read_text());require(manifest['trace_setup_sha256']==sha(setup) and manifest['session_token']==entries['etc/lynx/session-token']['data'].decode().strip(),'Source/token mismatch')
    for name in ['runtime_sha256','target_delays_seconds','result_codes','worker_sample_seconds','observation_seconds','timing_match_tolerance_seconds']:
        require(manifest[name]==prior_manifest[name],'Unrelated runtime/timing change: '+name)
    labels=['ufs_mtk_setup_ref_clk entry','before firmware call (+0x88)','after firmware call (+0x8c)','before request register store (+0xa0)','after request register store (+0xa4)','before acknowledgement register read (+0xf0)','after acknowledgement register read (+0xf8)','ufs_mtk_setup_ref_clk returned','ufs_mtk_boost_crypt entry'];require(manifest['trace_event_symbols']=={str(i):name for i,name in enumerate(labels,1)} and manifest['trace_events_all_ufs_specific'],'Event mapping changed')
    native=[p for p in sorted((P/'artifacts').glob('emulated-native-refclk-trace-v2-*/result.json')) if json.loads(p.read_text()).get('passed') and json.loads(p.read_text()).get('setup_source_sha256')==sha(setup)];require(native,'Passing native activation test missing')
    control=[p for p in sorted((R/'tools/test-artifacts').glob('refclk-v2-controlled-probe-*/result.json')) if json.loads(p.read_text()).get('passed') and json.loads(p.read_text()).get('source_sha256')==sha(setup)];require(control,'Matching probe-safety test missing')
    guards=sorted((P/'artifacts').glob('emulated-refclk-v2-probe-guard-*/result.json'));require(guards,'Exact image guard missing');g=json.loads(guards[-1].read_text());require(g['candidate_sha256']==SHA and g['module_checkpoint_failure_guard_observed'] and not g['kernel_reboot_command_observed'],'Reset guard failed')
    audit=json.loads((P/'docs/stock-ufs-refclk-audit.json').read_text());require(audit['module_sha256']=='31e452411297a57a6ed4c31b207c3b4604fa8b55acd95cff6135c680846614a4','Offset audit changed')
    rows=next(f for f in audit['functions'] if f['function']['name']=='ufs_mtk_setup_ref_clk')['instructions'];insns={r['offset']:r for r in rows}
    for offset,name in [(0x88,'bl'),(0x8c,'dmb'),(0xa0,'str'),(0xa4,'b'),(0xf0,'ldr'),(0xf8,'dmb')]:require(insns[offset]['mnemonic']==name,'Audited instruction boundary changed')
    require(insns[0x88]['relocation']['symbol']=='__arm_smccc_smc','Firmware call target changed')
    model=R/'tools/avb-host/avb-boot-model';mref=json.loads((P/'docs/avb-boot-model-results.json').read_text());require(sha(model.read_bytes())==mref['binary_sha256'],'Boot model changed')
    for unlocked in ['0','1']:
        result=subprocess.run([str(model),str(P/'artifacts/stock-cph2493-August-eu-ota'),str(F/'nord3-busybox-candidate.img'),'0',unlocked],capture_output=True,text=True,timeout=30);require(result.returncode==0 and json.loads(result.stdout)['slot_data_returned']==(unlocked=='1'),'Boot policy changed')
    report=dict(passed=True,candidate_sha256=SHA,native_receipt=str(native[-1]),control_receipt=str(control[-1]),guard_receipt=str(guards[-1]),phone_contacted=False,limits='Trace definitions and instruction boundaries verified in exact stock module. VM activation does not prove physical execution; RAM tracing can affect timing. No driver/firmware logic or partition foundation changed.')
    out=P/'docs/refclk-v2-probe-validation.json';out.write_text(json.dumps(report,indent=2)+'\n');print(out)
if __name__=='__main__':main()
