"""Independently validate one stock startup-module addition and its guards."""
import hashlib,json,stat,struct,subprocess,sys
from pathlib import Path
R=Path(__file__).resolve().parent.parent;P=R/'linux-port';sys.path.insert(0,str(P))
from image_formats import read_boot_v4,read_newc,require
from ramdisk_codec import decompress
SHA='b161edddb4a1a6a2e572f16298397f162d14f2d3e888220e58b576c5c4c0fe76'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def main():
    check=subprocess.run(['python3',str(R/'tools/validate_refclk_v2_probe_image.py')],capture_output=True,text=True,timeout=90);require(check.returncode==0,'Parent image validation failed: '+check.stdout+check.stderr)
    F=P/'artifacts/busybox-stock-clock-helper-probe-v1';REF=P/'artifacts/busybox-refclk-trace-probe-v2'
    image=(F/'nord3-busybox-candidate.img').read_bytes();reference=(REF/'nord3-busybox-candidate.img').read_bytes();require(sha(image)==SHA and len(image)==67108864,'Pinned image changed')
    require(stat.S_IMODE(F.stat().st_mode)==0o700 and stat.S_IMODE((F/'nord3-busybox-candidate.img').stat().st_mode)==0o600,'Private permissions changed')
    boot,prior=read_boot_v4(image),read_boot_v4(reference);require(boot['kernel']==prior['kernel'] and boot['cmdline']==prior['cmdline'],'Kernel/cmdline changed');require(image[:12]==reference[:12] and image[16:4096]==reference[16:4096],'Header geometry changed')
    entries,old=read_newc(decompress(boot['ramdisk'])),read_newc(decompress(prior['ramdisk']));require(set(entries)==set(old) and {n for n in old if entries[n]!=old[n]}=={'init','etc/lynx/session-token','etc/lynx/diag-codebook.json'},'Unrelated archive changes')
    guard=(P/'stock-clock-helper-guard.sh').read_bytes();runtime=(P/'lynx-stock-clock-helper-probe-runtime.sh').read_bytes();previous=(P/'lynx-ufs-trace-probe-runtime.sh').read_bytes()
    require(old['init']['data'].count(previous)==1 and entries['init']['data']==old['init']['data'].replace(previous,guard+runtime)==(F/'init-source').read_bytes(),'Executable source differs')
    expected_addition=b'''        lynx_stock_clock_helper_load
        clock_helper_status=$?
        if [ "$clock_helper_status" != 0 ]; then
            case "$clock_helper_status" in 10|11|12|13) ;; *) clock_helper_status=5 ;; esac
            lynx_ufs_registration_state "$clock_helper_status"
            exit 1
        fi
'''
    boundary=b"        log 'UFS_REGISTRATION_STOCK_MODULE_BEGIN'\n"
    expected_runtime=previous.replace(boundary,expected_addition+boundary).replace(b'in 0|1|2|3|4|5|6|7|8|9)',b'in 0|1|2|3|4|5|6|7|8|9|10|11|12|13)');require(runtime==expected_runtime,'Probe/reset flow changed beyond reviewed helper guard')
    coverage=struct.unpack('!4sIIQQQ28x',reference[-64:])[3];require(image[coverage:]==reference[coverage:],'Stock metadata/footer/payload changed');require(4096+((len(boot['kernel'])+4095)//4096)*4096+((len(boot['ramdisk'])+4095)//4096)*4096<=coverage,'Metadata overlap')
    manifest=json.loads((F/'build-validation.json').read_text());prior_manifest=json.loads((REF/'build-validation.json').read_text());require(manifest['clock_guard_sha256']==sha(guard) and manifest['runtime_sha256']==sha(runtime) and manifest['session_token']==entries['etc/lynx/session-token']['data'].decode().strip(),'Source or token mismatch')
    for key in ['trace_setup_sha256','trace_event_symbols','worker_sample_seconds','observation_seconds','timing_match_tolerance_seconds']:require(manifest[key]==prior_manifest[key],'Unrelated trace/timing change: '+key)
    codes=dict(prior_manifest['result_codes']);codes.update({'10':'stock clock helper guard refused; no UFS probe requested','11':'stock clock helper insertion failed; no UFS probe requested','12':'stock clock helper not bound; no UFS probe requested','13':'bus clock framework counts unavailable or zero; no UFS probe requested'});require(manifest['result_codes']==codes and manifest['target_delays_seconds']=={str(i):120+5*i for i in range(14)},'Outcome/timing map changed')
    book=json.loads(old['etc/lynx/diag-codebook.json']['data']);book['516']='stock clock helper: before load1, load returned2, bound and bus counters enabled3';require(json.loads(entries['etc/lynx/diag-codebook.json']['data'])==book==manifest['diagnostic_codebook'],'Hex codebook changed')
    auditcheck=subprocess.run(['python3',str(R/'tools/audit_stock_clock_helper.py')],capture_output=True,text=True,timeout=30);require(auditcheck.returncode==0,'Exact helper audit failed')
    audit=json.loads(auditcheck.stdout);require(audit['passed'] and audit['module_sha256']==manifest['stock_clock_helper_sha256']=='4b62b692837be57cc9aab66136dec5d772840c8f572c37c20c59bda979216823','Helper ABI/hash changed')
    vendor=read_newc(decompress((P/'artifacts/stock-cph2493-August-eu-ota/unpacked-vendor-boot/vendor_ramdisk00').read_bytes()));merged={**vendor,**entries};require(sha(merged['lib/modules/clk-bringup.ko']['data'])==audit['module_sha256'],'Provided vendor helper changed')
    require(audit['target']=='/clkitg/bring-up' and audit['clock_property_sha256']=='c6c820b927cb362d545b5798b35dec002e60f50805a78d4cc81ad7e90b698e9b','DT target changed')
    native=[p for p in sorted((P/'artifacts').glob('emulated-native-stock-clock-helper-*/result.json')) if json.loads(p.read_text()).get('passed') and json.loads(p.read_text()).get('source_sha256')==sha(guard) and json.loads(p.read_text()).get('candidate_sha256')==SHA];require(native,'Matching native guard/module test missing')
    controls=[p for p in sorted((R/'tools/test-artifacts').glob('stock-clock-helper-probe-control-*/result.json')) if json.loads(p.read_text()).get('passed') and json.loads(p.read_text()).get('source_sha256')==sha(runtime)];require(controls,'Matching supervisor test missing')
    guards=sorted((P/'artifacts').glob('emulated-stock-clock-helper-probe-guard-*/result.json'));require(guards,'Exact image guard missing');g=json.loads(guards[-1].read_text());require(g['candidate_sha256']==SHA and g['module_checkpoint_failure_guard_observed'] and not g['kernel_reboot_command_observed'],'Reset guard failed')
    require(json.loads((P/'docs/stock-clock-helper-probe-timing-test.json').read_text())['passed'],'Timing test failed')
    model=R/'tools/avb-host/avb-boot-model';mref=json.loads((P/'docs/avb-boot-model-results.json').read_text());require(sha(model.read_bytes())==mref['binary_sha256'],'Boot model changed')
    for unlocked in ['0','1']:
        result=subprocess.run([str(model),str(P/'artifacts/stock-cph2493-August-eu-ota'),str(F/'nord3-busybox-candidate.img'),'0',unlocked],capture_output=True,text=True,timeout=30);require(result.returncode==0 and json.loads(result.stdout)['slot_data_returned']==(unlocked=='1'),'Boot policy changed')
    out=P/'docs/stock-clock-helper-probe-validation.json';report=dict(passed=True,candidate_sha256=SHA,native_receipt=str(native[-1]),control_receipt=str(controls[-1]),guard_receipt=str(guards[-1]),phone_contacted=False,limits='Stock clock helper/target/ABI and guarded flow verified; physical clock enabling and UFS access remain unproved. Framework counts are not hardware measurements. All foundation partitions and stock driver bytes preserved.')
    out.write_text(json.dumps(report,indent=2)+'\n');print(out)
if __name__=='__main__':main()
