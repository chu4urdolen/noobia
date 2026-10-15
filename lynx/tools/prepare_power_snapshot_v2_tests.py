"""Prepare wider-slot snapshot tests, exact module failures and scoped trial."""
from pathlib import Path
T=Path(__file__).resolve().parent
OLD='d68afb3526a28a81c41a0b1b85a4816f85269fddb80c5eac11caadc5402ab598'
NEW='a19be93f2ae73debfb51dfd02e582ba97b31d882491ea10f2a05790db4efa9df'
def save(name,text):
    path=T/name;assert not path.exists();compile(text,str(path),'exec');path.write_text(text)
control=(T/'test_power_snapshot_control.py').read_text().replace('lynx-power-snapshot-runtime.sh','lynx-power-snapshot-v2-runtime.sh').replace('power-snapshot-control-','power-snapshot-v2-control-')
control=control.replace("('base-failed',16),('base-pending',17),('query-pending',18)","('base-failed',33),('base-pending',32),('query-pending',67),('persistent-log-interface',31)")
control=control.replace("(folder/'driver').mkdir();", "(folder/'pstore').mkdir()\n    if mode=='persistent-log-interface':(folder/'pstore/fixture-record').write_text('fixture only')\n    (folder/'driver').mkdir();")
control=control.replace(".replace('/proc/sysrq-trigger',str(folder/'interface'))", ".replace('/proc/sysrq-trigger',str(folder/'interface')).replace('/sys/fs/pstore',str(folder/'pstore')).replace('/proc/last_kmsg',str(folder/'last_kmsg'))")
save('test_power_snapshot_v2_control.py',control)
native=(T/'test_native_power_snapshot.py').read_text().replace(OLD,NEW).replace('busybox-power-metadata-snapshot-v1','busybox-power-metadata-snapshot-v2').replace('lynx-power-snapshot-runtime.sh','lynx-power-snapshot-v2-runtime.sh').replace('emulated-native-power-snapshot-','emulated-native-power-snapshot-v2-')
native=native.replace('120+2*progress_code','120+5*progress_code').replace('snapshot_mask=15','snapshot_mask=31').replace('code=15 target_delay=20','code=31 target_delay=20').replace("'16'","'66'")
save('test_native_power_snapshot_v2.py',native)
guard=(T/'test_power_snapshot_guard.py').read_text().replace('busybox-power-metadata-snapshot-v1','busybox-power-metadata-snapshot-v2').replace('emulated-power-snapshot-guard-','emulated-power-snapshot-v2-guard-')
save('test_power_snapshot_v2_guard.py',guard)
validator=(T/'validate_power_snapshot_image.py').read_text().replace(OLD,NEW).replace('busybox-power-metadata-snapshot-v1','busybox-power-metadata-snapshot-v2').replace('lynx-power-snapshot-runtime.sh','lynx-power-snapshot-v2-runtime.sh').replace('power-snapshot-control-','power-snapshot-v2-control-').replace('emulated-native-power-snapshot-','emulated-native-power-snapshot-v2-').replace('emulated-power-snapshot-guard-','emulated-power-snapshot-v2-guard-')
validator=validator.replace("8:'SysRq permission check writable'", "8:'SysRq permission check writable',16:'persistent log file interface present'").replace('range(16):','range(32):').replace('range(128)','range(70)').replace('120+2*n','120+5*n')
validator=validator.replace("codes.update({'16':'known base module insertion failed','17':'known base module prefix still pending','18':'metadata query pending','125':'malformed progress record','127':'worker progress unavailable'})", "codes.update({str(32+i):'base insertion failed: '+name for i,name in enumerate(prefix,1)});codes.update({'32':'known base module prefix still pending','67':'metadata query pending','68':'malformed progress record','69':'worker progress unavailable'})")
validator=validator.replace("manifest['observation_seconds']==420", "manifest['observation_seconds']==540").replace("manifest['timing_match_tolerance_seconds']==0.8", "manifest['timing_match_tolerance_seconds']==2.0")
validator=validator.replace('power-snapshot-timing-test.json','power-snapshot-v2-timing-test.json').replace('lynx_progress_timing.py','lynx_power_snapshot_v2_timing.py').replace('power-snapshot-validation.json','power-snapshot-v2-validation.json')
save('validate_power_snapshot_v2_image.py',validator)
trial=(T/'lynx_boot_a_power_snapshot_trial.py').read_text().replace(OLD,NEW).replace('busybox-power-metadata-snapshot-v1','busybox-power-metadata-snapshot-v2').replace('validate_power_snapshot_image.py','validate_power_snapshot_v2_image.py').replace('boot-a-power-snapshot-trial-','boot-a-power-snapshot-v2-trial-').replace('from lynx_progress_timing import','from lynx_power_snapshot_v2_timing import').replace('420 seconds','540 seconds').replace('time.monotonic()+420','time.monotonic()+540').replace('0<=field<16','0<=field<32')
trial=trial.replace("'sysrq_permission_writable':bool(field&8)", "'sysrq_permission_writable':bool(field&8),'persistent_log_file_interface_present':bool(field&16)")
save('lynx_boot_a_power_snapshot_v2_trial.py',trial)
print('Wider snapshot tests and trial prepared; no phone contacted.')
