"""Prepare pinned retained-log query validation and scoped trial."""
import hashlib,json
from pathlib import Path
T=Path(__file__).resolve().parent;P=T.parent/'linux-port'
OLD='a19be93f2ae73debfb51dfd02e582ba97b31d882491ea10f2a05790db4efa9df'
NEW='3f713d6949c9e5c6fcab86e76b8b22e7c949bc45f0b140fa6ac74c6d85287412'
def save(name,text):
    path=T/name;assert not path.exists();compile(text,str(path),'exec');path.write_text(text)
reference=json.loads((P/'artifacts/busybox-retained-log-query-v1/build-validation.json').read_text())['reference_ufs_token']
payload=f'LXDG1 {reference} 00000001 0000000a 0200 0029';raw=(payload+' '+hashlib.sha256(payload.encode()).hexdigest()+'\nKernel panic - not syncing: fixture\nCFI failure at fixture\nCall trace:\n ufs_mtk_init+0x10/0x20\n').encode()
native=(T/'test_native_power_snapshot_v2.py').read_text().replace(OLD,NEW).replace('busybox-power-metadata-snapshot-v2','busybox-retained-log-query-v1').replace('lynx-power-snapshot-v2-runtime.sh','lynx-retained-log-runtime.sh').replace('emulated-native-power-snapshot-v2-','emulated-native-retained-log-')
native=native.replace("replace(b'/bin/boot-proof-reboot',b'/bin/progress-reset')", "replace(b'/bin/boot-proof-reboot',b'/bin/progress-reset').replace(b'/sys/fs/pstore',b'/fixture/pstore').replace(b'/proc/last_kmsg',b'/fixture/no-last-kmsg')")
native=native.replace("    init=b'''", "    put(entries,'fixture',b'',0o40700);put(entries,'fixture/pstore',b'',0o40700);put(entries,'fixture/pstore/sample',"+repr(raw)+",0o100600)\n    init=b'''")
native=native.replace('lynx_power_snapshot() { snapshot_mask=31; }\n','').replace('code=31 target_delay=20','code=63 target_delay=20').replace('code=12 target_delay=20','code=0 target_delay=20')
native=native.replace('$BB rm /run/fail-clock /run/lynx/module-progress','$BB rm /run/fail-clock /run/lynx/module-progress /fixture/pstore/sample')
save('test_native_retained_log.py',native)
guard=(T/'test_power_snapshot_v2_guard.py').read_text().replace('busybox-power-metadata-snapshot-v2','busybox-retained-log-query-v1').replace('emulated-power-snapshot-v2-guard-','emulated-retained-log-guard-')
save('test_retained_log_guard.py',guard)
validator=(T/'validate_power_snapshot_v2_image.py').read_text().replace(OLD,NEW).replace('busybox-power-metadata-snapshot-v2','busybox-retained-log-query-v1').replace('lynx-power-snapshot-v2-runtime.sh','lynx-retained-log-runtime.sh').replace('power-snapshot-v2-control-','retained-log-control-').replace('emulated-native-power-snapshot-v2-','emulated-native-retained-log-').replace('emulated-power-snapshot-v2-guard-','emulated-retained-log-guard-')
validator=validator.replace("{'etc/lynx/progress-modules.load','etc/lynx/progress-count'}", "{'etc/lynx/progress-modules.load','etc/lynx/progress-count','etc/lynx/reference-ufs-token'}")
start=validator.index('    flags={');end=validator.index("    require(manifest['session_token']",start)
codes="""    flags={1:'bounded record data read',2:'failed-UFS token text present',4:'matching stage checksum valid',8:'panic/oops marker present',16:'CFI failure marker present',32:'UFS/power/clock/SMC call-trace marker present'}
    codes={str(i):'reserved; do not interpret' for i in range(70)}
    for code in range(64):
        if code and not code&1:continue
        if code&4 and not code&2:continue
        codes[str(code)]='selected retained record: '+(', '.join(text for bit,text in flags.items() if code&bit) or 'no nonempty record read')
    codes.update({'64':'known base prefix pending','65':'bounded log query pending','66':'base module insertion failed','68':'malformed progress/reference record','69':'worker progress unavailable'})
    require(manifest['result_codes']==codes and manifest['retained_log_query'],'Log query interpretation differs')
    reference_token=json.loads((P/'artifacts/busybox-ufs-probe-emergency-v1/build-validation.json').read_text())['session_token']
    require(current['etc/lynx/reference-ufs-token']['data']==reference_token.encode()+bytes([10]) and manifest['reference_ufs_token']==reference_token,'Reference experiment differs')
    require(b\"printf 'b'\" not in source and b\"printf 'h'\" not in source and source.count(b'/bin/boot-proof-reboot')==1,'Reset scope differs')
    require(b'head -c 1048576' in source and b'log_index\\\" -le 8' in source,'Read bounds differ')
"""
validator=validator[:start]+codes+validator[end:]
validator=validator.replace('power-snapshot-v2-timing-test.json','retained-log-timing-test.json').replace('power-snapshot-v2-validation.json','retained-log-validation.json')
save('validate_retained_log_image.py',validator)
trial=(T/'lynx_boot_a_power_snapshot_v2_trial.py').read_text().replace(OLD,NEW).replace('busybox-power-metadata-snapshot-v2','busybox-retained-log-query-v1').replace('validate_power_snapshot_v2_image.py','validate_retained_log_image.py').replace('boot-a-power-snapshot-v2-trial-','boot-a-retained-log-trial-').replace('read-only controller binding/domain object/debugfs/reset permission snapshot; no main UFS load','bounded retained kernel log query; original failed-UFS reference; no main UFS/radio/block access')
trial=trial.replace('0<=field<32','0<=field<64').replace("report['power_metadata_flags']={'controller_bound':bool(field&1),'ufs0_domain_object_present':bool(field&2),'debugfs_mounted':bool(field&4),'sysrq_permission_writable':bool(field&8),'persistent_log_file_interface_present':bool(field&16)}", "report['retained_log_flags']={'nonempty_data_read':bool(field&1),'reference_token_text':bool(field&2),'reference_stage_checksum_valid':bool(field&4),'panic_oops_marker':bool(field&8),'cfi_failure_marker':bool(field&16),'ufs_power_clock_smc_call_trace_marker':bool(field&32)}")
save('lynx_boot_a_retained_log_trial.py',trial)
timing=(T/'test_power_snapshot_v2_timing.py').read_text().replace('busybox-power-metadata-snapshot-v2','busybox-retained-log-query-v1').replace('power-snapshot-v2-timing-test.json','retained-log-timing-test.json')
timing=timing.replace('[130,135,170,175,212.5,227.5,452.5]','[130,140,150,160,170,212.5,227.5]')
save('test_retained_log_timing.py',timing)
print('Retained log tests and scoped trial prepared; no phone contacted.')
