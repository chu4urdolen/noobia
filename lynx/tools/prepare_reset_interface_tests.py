"""Prepare pinned normal-reset-only interface test, validation and trial."""
from pathlib import Path
T=Path(__file__).resolve().parent
OLD='465fa84fd647dc04298565db906bcbad3794166d247900bd2246d24702a521d2'
NEW='ea2715f2f7ec48f56fcdc42d1a380b8aeba030db5903d0a6b89acaee11f107ce'
def save(name,text):
    path=T/name;assert not path.exists();compile(text,str(path),'exec');path.write_text(text)
native=(T/'test_native_module_progress_debug_32.py').read_text().replace('choices=[0,28,32]','choices=[0]').replace(OLD,NEW).replace("'busybox-module-progress-debug-'+str(args.count)+'-v1'", "'busybox-reset-interface-v1'").replace('lynx-module-progress-debug-runtime.sh','lynx-reset-interface-runtime.sh').replace('emulated-native-module-progress-debug-v2-','emulated-native-reset-interface-')
native=native.replace('echo NATIVE_PROGRESS_FAILURE_BEGIN',"''' + fixture.replace(b'/proc/sysrq-trigger',b'/run/missing-reset-interface') + b'''\necho NATIVE_PROGRESS_FAILURE_BEGIN")
native=native.replace("('108' if args.count else '0')", "'2'").replace("'prefix_success':", "'real_sysrq_help':b'sysrq: HELP' in raw,'prefix_success':")
save('test_native_reset_interface.py',native)
guard=(T/'test_module_progress_debug_32_guard.py').read_text().replace('choices=[0,28,32]','choices=[0]').replace("'busybox-module-progress-debug-'+str(args.count)+'-v1'", "'busybox-reset-interface-v1'").replace('emulated-module-progress-debug-guard-','emulated-reset-interface-guard-')
save('test_reset_interface_guard.py',guard)
validator=(T/'validate_progress_debug_32_image.py').read_text().replace('choices=[0,28,32]','choices=[0]').replace(OLD,NEW).replace("'busybox-module-progress-debug-'+str(args.count)+'-v1'", "'busybox-reset-interface-v1'").replace('lynx-module-progress-debug-runtime.sh','lynx-reset-interface-runtime.sh').replace('module-progress-debug-control-','reset-interface-control-').replace('emulated-native-module-progress-debug-','emulated-native-reset-interface-').replace('emulated-module-progress-debug-guard-','emulated-reset-interface-guard-')
extra="""    codes={str(i):'reserved; do not interpret' for i in range(128)}
    codes.update({'0':'SysRq help write accepted; emergency reset not executed','1':'SysRq help write rejected','2':'SysRq interface absent','3':'SysRq help request pending at sample','125':'malformed progress record','127':'worker progress unavailable'})
    require(manifest['result_codes']==codes and manifest['reset_interface_check'] and not manifest['calibration_only'] and not prefix,'Interface profile differs')
    require(source.count(b\"printf 'h' > /proc/sysrq-trigger\")==1 and b\"printf 'b'\" not in source,'Harmless write scope differs')
"""
validator=validator.replace("    require(manifest['session_token']",extra+"    require(manifest['session_token']")
validator=validator.replace("n['checks']['native_hex_FAILURE']", "n['checks']['native_hex_FAILURE'] and n['checks']['real_sysrq_help']")
validator=validator.replace("'module-progress-debug-'+str(args.count)+'-validation.json'", "'reset-interface-validation.json'")
save('validate_reset_interface_image.py',validator)
trial=(T/'lynx_boot_a_progress_debug_0_trial.py').read_text().replace('busybox-module-progress-debug-0-v1','busybox-reset-interface-v1').replace(OLD,NEW).replace('validate_progress_debug_image.py','validate_reset_interface_image.py').replace('boot-a-progress-debug-0-trial-','boot-a-reset-interface-trial-').replace('from lynx_progress_timing import','from lynx_reset_interface_timing import')
trial=trial.replace('    calibrated_baseline=None',"    calibrated_baseline=None\n    if args.flash_linux:\n        calibration=json.loads((PROJECT/'docs/progress-debug-calibration.json').read_text())\n        if not calibration.get('passed') or calibration.get('calibration_image_sha256')!='"+OLD+"':raise ValueError('Verified original debug baseline required')\n        calibrated_baseline=calibration['baseline_seconds']")
save('lynx_boot_a_reset_interface_trial.py',trial)
print('Reset interface tests and trial prepared; no phone contacted.')
