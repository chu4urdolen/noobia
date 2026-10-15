"""Prepare stage-marker selection tests, validation and scoped trial."""
from pathlib import Path
T=Path(__file__).resolve().parent
OLD='3f713d6949c9e5c6fcab86e76b8b22e7c949bc45f0b140fa6ac74c6d85287412'
NEW='1dc206e7ba79067711957f9d8b40ea19d53594b38a4d7e51026275035262bc52'
def save(name,text):
    path=T/name;assert not path.exists();compile(text,str(path),'exec');path.write_text(text)
control=(T/'test_retained_log_control.py').read_text().replace('lynx-retained-log-runtime.sh','lynx-retained-stage-runtime.sh').replace('busybox-retained-log-query-v1','busybox-retained-stage-query-v1').replace('retained-log-control-','retained-stage-control-')
control=control.replace("('unrelated',1,", "('unrelated',0,").replace("('invalid-checksum',3,","('invalid-checksum',0,").replace("('valid-frame',7,","('valid-frame',1,").replace("('matching-crash',63,","('matching-crash',1,").replace("('no-cross-file-mixing',7,","('no-cross-file-mixing',1,").replace("('prefer-valid-reference',7,","('prefer-valid-reference',1,").replace("('eight-file-limit',1,","('eight-file-limit',0,").replace("('one-megabyte-limit',1,","('one-megabyte-limit',0,").replace("('base-failed',66,","('base-failed',128,").replace("('base-pending',64,","('base-pending',126,").replace("('query-pending',65,","('query-pending',127,")
control=control.replace("(folder/'reference').write_text(reference+'\\n')", "(folder/'reference').write_text(reference+'\\n');(folder/'progress-map').write_bytes((P/'artifacts/busybox-retained-stage-query-v1/reference-progress-map').read_bytes())")
control=control.replace(".replace('/etc/lynx/reference-ufs-token',str(folder/'reference'))", ".replace('/etc/lynx/reference-ufs-token',str(folder/'reference')).replace('/etc/lynx/reference-progress-map',str(folder/'progress-map'))")
extra="""def make_frame(status,sequence=2,stage=512):
    p=f'LXDG1 {reference} {sequence:08x} 0000000a {stage:04x} {status:04x}'
    return p+' '+hashlib.sha256(p.encode()).hexdigest()+'\\n'
specs.extend([('last-completion',2,[frame+make_frame(83)]),('all-done',4,[frame+make_frame(0)]),('failure-marker',3,[make_frame(125)]),('ignore-other-stage',1,[frame+make_frame(0,stage=16)]),('ignore-invalid-last',1,[frame+bad]),('no-progress-stage',0,[make_frame(0,stage=16)])])
"""
control=control.replace('cases=[]', 'cases=[]',1).replace('for mode,expected,records in specs:',extra+'for mode,expected,records in specs:')
save('test_retained_stage_control.py',control)
native=(T/'test_native_retained_log.py').read_text().replace(OLD,NEW).replace('busybox-retained-log-query-v1','busybox-retained-stage-query-v1').replace('lynx-retained-log-runtime.sh','lynx-retained-stage-runtime.sh').replace('emulated-native-retained-log-','emulated-native-retained-stage-').replace('code=63 target_delay=20','code=1 target_delay=20').replace("'66'","'128'")
save('test_native_retained_stage.py',native)
guard=(T/'test_retained_log_guard.py').read_text().replace('busybox-retained-log-query-v1','busybox-retained-stage-query-v1').replace('emulated-retained-log-guard-','emulated-retained-stage-guard-')
save('test_retained_stage_guard.py',guard)
validator=(T/'validate_retained_log_image.py').read_text().replace(OLD,NEW).replace('busybox-retained-log-query-v1','busybox-retained-stage-query-v1').replace('lynx-retained-log-runtime.sh','lynx-retained-stage-runtime.sh').replace('retained-log-control-','retained-stage-control-').replace('emulated-native-retained-log-','emulated-native-retained-stage-').replace('emulated-retained-log-guard-','emulated-retained-stage-guard-')
validator=validator.replace("'etc/lynx/reference-ufs-token'}", "'etc/lynx/reference-ufs-token','etc/lynx/reference-progress-map'}")
start=validator.index('    flags={');end=validator.index("    require(b\"printf 'b'\"",start)
replacement="""    reference_manifest=json.loads((P/'artifacts/busybox-ufs-probe-emergency-v1/build-validation.json').read_text());reference_codes=reference_manifest['result_codes']
    statuses=[41,83,125,0]+[n for n in range(len(reference_codes)) if n not in [41,83,125,0] and not reference_codes[str(n)].startswith('reserved')]
    progress_map={str(i):n for i,n in enumerate(statuses,1)}
    codes={str(n):'reserved; do not interpret' for n in range(131)};codes['0']='no checksum-valid reference progress marker found in selected bounded record'
    for code,status in progress_map.items():codes[code]='last retained reference marker: '+reference_codes[str(status)]
    codes.update({'126':'known base prefix pending','127':'retained stage query pending','128':'base module insertion failed','129':'reference/progress map invalid','130':'worker progress unavailable'})
    require(manifest['result_codes']==codes and manifest['retained_stage_query'] and manifest['reference_progress_map']==progress_map,'Retained stage mapping differs')
    reference_token=reference_manifest['session_token']
    require(current['etc/lynx/reference-ufs-token']['data']==reference_token.encode()+bytes([10]) and manifest['reference_ufs_token']==reference_token,'Reference token differs')
    map_bytes=''.join(str(status)+' '+code+chr(10) for code,status in progress_map.items()).encode()
    require(current['etc/lynx/reference-progress-map']['data']==map_bytes,'Executable reference map differs')
"""
validator=validator[:start]+replacement+validator[end:]
validator=validator.replace('range(70)','range(131)').replace("manifest['observation_seconds']==540","manifest['observation_seconds']==900").replace('retained-log-timing-test.json','retained-stage-timing-test.json').replace('lynx_power_snapshot_v2_timing.py','lynx_retained_stage_timing.py').replace('retained-log-validation.json','retained-stage-validation.json')
save('validate_retained_stage_image.py',validator)
timing_decoder=(T/'lynx_power_snapshot_v2_timing.py').read_text().replace('range(70)','range(131)').replace('Snapshot v2 grid changed','Retained stage grid changed')
timing_decoder=timing_decoder.replace('Domain object is not power-on/provider proof; log interface presence is not readable retained data.','Last verified marker in one bounded reference record, not exact instruction stop, complete sequence or guaranteed newest boot across files.')
save('lynx_retained_stage_timing.py',timing_decoder)
trial=(T/'lynx_boot_a_retained_log_trial.py').read_text().replace(OLD,NEW).replace('busybox-retained-log-query-v1','busybox-retained-stage-query-v1').replace('validate_retained_log_image.py','validate_retained_stage_image.py').replace('boot-a-retained-log-trial-','boot-a-retained-stage-trial-').replace('from lynx_power_snapshot_v2_timing import','from lynx_retained_stage_timing import').replace('540 seconds','900 seconds').replace('time.monotonic()+540','time.monotonic()+900')
start=trial.index('            if field is not None and 0<=field<64:');end=trial.index("\n\n        report['stock_undo_pending']",start)
trial=trial[:start]+"            if field is not None and str(field) in manifest['reference_progress_map']:\n                report['retained_reference_progress_status']=manifest['reference_progress_map'][str(field)]\n"+trial[end:]
save('lynx_boot_a_retained_stage_trial.py',trial)
timing=(T/'test_retained_log_timing.py').read_text().replace('busybox-retained-log-query-v1','busybox-retained-stage-query-v1').replace('from lynx_power_snapshot_v2_timing import','from lynx_retained_stage_timing import').replace('retained-log-timing-test.json','retained-stage-timing-test.json').replace('lynx_power_snapshot_v2_timing.py','lynx_retained_stage_timing.py')
timing=timing.replace('[130,140,150,160,170,212.5,227.5]','[752.5,757.5,762.5,767.5,772.5,777.5,782.5]')
save('test_retained_stage_timing.py',timing)
print('Retained stage tests and scoped trial prepared; no phone contacted.')
