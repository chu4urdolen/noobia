"""Pin snapshot control tests, validation and boot_a-only trial."""
from pathlib import Path
T=Path(__file__).resolve().parent
OLD='6070a324cbbfc8a1262b94ae111e3a6b3a4cb330e66af54d2363a3e2c5b7edad'
NEW='d68afb3526a28a81c41a0b1b85a4816f85269fddb80c5eac11caadc5402ab598'
def save(name,text):
    path=T/name;assert not path.exists();compile(text,str(path),'exec');path.write_text(text)
native=(T/'test_native_power_controller_progress.py').read_text().replace('choices=[0,28,32,34]','choices=[34]').replace(OLD,NEW).replace("'busybox-module-progress-debug-'+str(args.count)+'-v1'", "'busybox-power-metadata-snapshot-v1'").replace('lynx-power-controller-progress-runtime.sh','lynx-power-snapshot-runtime.sh').replace('emulated-native-module-progress-debug-v2-','emulated-native-power-snapshot-')
native=native.replace('echo NATIVE_PROGRESS_SUCCESS_BEGIN','lynx_power_snapshot() { snapshot_mask=15; }\necho NATIVE_PROGRESS_SUCCESS_BEGIN').replace('code=0 target_delay=20','code=15 target_delay=20').replace("('114' if args.count else '0')","'16'")
native=native.replace('$BB poweroff -f',"''' + fixture + b'''\n$BB rm /run/fail-clock /run/lynx/module-progress\necho NATIVE_PROGRESS_QUERY_BEGIN\nlynx_module_progress\necho NATIVE_QUERY_HEX_BEGIN\n$BB cat /run/lynx/stages-bootstrap.hex\necho NATIVE_QUERY_HEX_END\n$BB cat /run/lynx/boot.log\n$BB poweroff -f")
native=native.replace('timeout=60','timeout=90').replace("['SUCCESS','FAILURE']","['SUCCESS','FAILURE','QUERY']").replace('==2,','==3,').replace('exactly_two_fake_resets','exactly_three_fake_resets').replace("'prefix_success':","'real_vm_query':b'MODULE_PROGRESS_FIELD code=12 target_delay=20' in raw,'prefix_success':")
save('test_native_power_snapshot.py',native)
guard=(T/'test_power_controller_progress_guard.py').read_text().replace('choices=[0,28,32,34]','choices=[34]').replace("'busybox-module-progress-debug-'+str(args.count)+'-v1'", "'busybox-power-metadata-snapshot-v1'").replace('emulated-module-progress-debug-guard-','emulated-power-snapshot-guard-')
save('test_power_snapshot_guard.py',guard)
validator=(T/'validate_power_controller_progress_image.py').read_text().replace('choices=[0,28,32,34]','choices=[34]').replace(OLD,NEW).replace("'busybox-module-progress-debug-'+str(args.count)+'-v1'", "'busybox-power-metadata-snapshot-v1'").replace('lynx-power-controller-progress-runtime.sh','lynx-power-snapshot-runtime.sh').replace('power-controller-progress-control-','power-snapshot-control-').replace('emulated-native-module-progress-debug-','emulated-native-power-snapshot-').replace('emulated-module-progress-debug-guard-','emulated-power-snapshot-guard-')
validator=validator.replace("n['checks']['native_hex_FAILURE']","n['checks']['native_hex_FAILURE'] and n['checks']['native_hex_QUERY'] and n['checks']['real_vm_query']")
extra="""    flags={1:'power-controller bound',2:'ufs0 domain object present',4:'debugfs mounted',8:'SysRq permission check writable'}
    codes={str(i):'reserved; do not interpret' for i in range(128)}
    for code in range(16):
        if code&2 and not code&4:continue
        codes[str(code)]='power metadata snapshot: '+(', '.join(text for bit,text in flags.items() if code&bit) or 'all queried flags absent')
    codes.update({'16':'known base module insertion failed','17':'known base module prefix still pending','18':'metadata query pending','125':'malformed progress record','127':'worker progress unavailable'})
    require(manifest['result_codes']==codes and manifest['power_metadata_snapshot'],'Snapshot interpretation differs')
    require(b\"printf 'b'\" not in source and b\"printf 'h'\" not in source and source.count(b'/bin/boot-proof-reboot')==1,'Snapshot reset scope differs')
    require(json.loads((P/'docs/power-domain-presence-audit.json').read_text())['passed'],'Read-only query source audit missing')
"""
validator=validator.replace("    require(manifest['session_token']",extra+"    require(manifest['session_token']").replace("'module-progress-debug-'+str(args.count)+'-validation.json'","'power-snapshot-validation.json'")
save('validate_power_snapshot_image.py',validator)
trial=(T/'lynx_boot_a_power_controller_progress_trial.py').read_text().replace('busybox-module-progress-debug-34-v1','busybox-power-metadata-snapshot-v1').replace(OLD,NEW).replace('validate_power_controller_progress_image.py','validate_power_snapshot_image.py').replace('boot-a-progress-debug-34-trial-','boot-a-power-snapshot-trial-').replace('stock power-controller library and driver with per-module checkpoints','read-only controller binding/domain object/debugfs/reset permission snapshot; no main UFS load')
save('lynx_boot_a_power_snapshot_trial.py',trial)
print('Snapshot tests and scoped trial prepared; no handset contacted.')
