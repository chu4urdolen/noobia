"""Pin main-UFS/fallback tests and scoped handset trial after local checks."""
from pathlib import Path
T=Path(__file__).resolve().parent
OLD='18a5250d0617c03a305381b6aa24e37a0f2681463e441f7771a586df4a2ec540'
NEW='f65ec3de06c76a85f7796492476c5eba89666aa79bf59c6c15a0037f615e7b60'
def save(name,text):
    path=T/name;assert not path.exists();compile(text,str(path),'exec');path.write_text(text)
def main():
    native=(T/'test_native_storage_prefix_progress.py').read_text().replace('choices=[40]','choices=[41]').replace("40:'"+OLD+"'}", "40:'"+OLD+"',41:'"+NEW+"'}")
    native=native.replace("'busybox-module-progress-debug-'+str(args.count)+'-v1'", "'busybox-ufs-probe-emergency-v1'").replace('lynx-storage-prefix-progress-runtime.sh','lynx-ufs-probe-progress-runtime.sh').replace('/lib/modules/blocktag.ko','/lib/modules/ufs-mediatek-mod.ko').replace("'120'","'125'").replace('emulated-native-storage-prefix-progress-','emulated-native-ufs-probe-progress-')
    native=native.replace("replace(b'/bin/boot-proof-reboot',b'/bin/progress-reset')", "replace(b'/bin/boot-proof-reboot',b'/bin/progress-reset').replace(b'/proc/sysrq-trigger',b'/run/fixture-sysrq')")
    native=native.replace("echo NATIVE_PROGRESS_SUCCESS_BEGIN", "$BB touch /run/fixture-sysrq\necho NATIVE_PROGRESS_SUCCESS_BEGIN")
    native=native.replace('timeout=60','timeout=75')
    native=native.replace("$BB poweroff -f", "echo NATIVE_SYSRQ_FIXTURE_BEGIN\n$BB cat /run/fixture-sysrq\necho NATIVE_SYSRQ_FIXTURE_END\n$BB poweroff -f")
    native=native.replace("'prefix_success':", "'fixture_emergency_requested':b'NATIVE_SYSRQ_FIXTURE_BEGIN\\r\\nbNATIVE_SYSRQ_FIXTURE_END' in raw,'prefix_success':")
    save('test_native_ufs_probe_progress.py',native)
    guard=(T/'test_storage_prefix_progress_guard.py').read_text().replace('choices=[40]','choices=[41]').replace("'busybox-module-progress-debug-'+str(args.count)+'-v1'", "'busybox-ufs-probe-emergency-v1'").replace('emulated-module-progress-debug-guard-','emulated-ufs-probe-guard-')
    save('test_ufs_probe_progress_guard.py',guard)
    validator=(T/'validate_essential_storage_progress_image.py').read_text().replace('476997a9b518d951f075194004cf288e0214741f571810f8932009b8c585d11e',NEW)
    validator=validator.replace("'busybox-module-progress-debug-'+str(args.count)+'-v1'", "'busybox-ufs-probe-emergency-v1'").replace('lynx-essential-storage-progress-runtime.sh','lynx-ufs-probe-progress-runtime.sh').replace('essential-storage-progress-control-','ufs-probe-progress-control-').replace('emulated-native-essential-storage-progress-','emulated-native-ufs-probe-progress-').replace("'emulated-module-progress-debug-guard-'+str(args.count)+'-*/result.json'", "'emulated-ufs-probe-guard-'+str(args.count)+'-*/result.json'")
    validator=validator.replace('all essential module insertions and verified own boot payload read completed','all essential module insertions completed; binding not proven')
    validator=validator.replace("'42':'partition discovery or own boot payload read pending','84':'own boot payload verified and extracted','126':'partition discovery or own boot payload read failed',",'')
    validator=validator.replace(" and n['checks']['native_hex_PAYLOAD'] and n['checks']['payload_failure']", " and n['checks']['fixture_emergency_requested']")
    extra="""    safety=json.loads((P/'docs/sysrq-reset-path.json').read_text());require(safety['passed'],'Emergency source audit failed')
    resets=sorted((P/'artifacts').glob('emulated-stock-sysrq-reset-*/result.json'));require(resets and json.loads(resets[-1].read_text())['passed'],'Stock kernel SysRq VM proof missing')
    require(manifest['emergency_reset_offset_seconds']==5 and manifest['payload_read_attempted'] is False,'Fallback profile differs')
    require(source.count(b'/bin/boot-proof-reboot &\\n')==1 and source.count(b\"printf 'b' > /proc/sysrq-trigger\")==1 and b'lynx_storage_payload_checkpoint' not in source,'Reset/read scope changed')
    timing=json.loads((P/'docs/probe-safe-timing-test.json').read_text());require(timing['passed'] and timing['decoder_sha256']==sha((ROOT/'tools/lynx_probe_safe_timing.py').read_bytes()),'Timing decoder not tested')
"""
    validator=validator.replace("    report={'passed':True",extra+"    report={'passed':True")
    validator=validator.replace("'module-progress-debug-'+str(args.count)+'-validation.json'", "'ufs-probe-emergency-validation.json'")
    save('validate_ufs_probe_progress_image.py',validator)
    trial=(T/'lynx_boot_a_essential_storage_trial.py').read_text().replace('busybox-module-progress-debug-41-v1','busybox-ufs-probe-emergency-v1').replace('476997a9b518d951f075194004cf288e0214741f571810f8932009b8c585d11e',NEW).replace('validate_essential_storage_progress_image.py','validate_ufs_probe_progress_image.py').replace('boot-a-essential-storage-trial-','boot-a-ufs-probe-trial-').replace('from lynx_progress_timing import','from lynx_probe_safe_timing import').replace('essential UFS modules and read-only verified own boot payload checkpoint','main UFS insertion only; one ordinary reset with guarded emergency fallback; no payload read')
    save('lynx_boot_a_ufs_probe_trial.py',trial)
    print('UFS/fallback tests prepared; no handset contacted.')
if __name__=='__main__':main()
