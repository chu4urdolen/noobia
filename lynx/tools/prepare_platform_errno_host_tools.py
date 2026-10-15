"""Prepare pinned validation and monotonic decoding for the errno trial."""
from pathlib import Path

T=Path(__file__).resolve().parent
OLD='aff51e9e74094d95fa0e2addbf3671326869a07eda2104f09b28821f8b07f56f'
NEW='8856714bafaabc6869ab58fa46194babcd055afd22b88ba93d3d0bf02901afaa'


def save(name,source):
    path=T/name;assert not path.exists(),'Preserve previous tools';path.write_text(source)


def main():
    vm=(T/'test_platform_probe_image_vm.py').read_text().replace('busybox-platform-probe-v1','busybox-platform-errno-v1').replace('emulated-platform-probe-image-','emulated-platform-errno-image-')
    save('test_platform_errno_image_vm.py',vm)
    validator=(T/'validate_platform_probe_image.py').read_text().replace('busybox-platform-probe-v1','busybox-platform-errno-v1').replace(OLD,NEW)
    validator=validator.replace('platform-probe-control-','platform-errno-control-').replace('emulated-platform-probe-image-','emulated-platform-errno-image-').replace('platform-probe-image-validation.json','platform-errno-image-validation.json')
    validator=validator.replace('lynx-classify-platform-trace.awk','lynx-classify-platform-errno.awk').replace('platform-trace-classifier-','platform-errno-classifier-')
    validator=validator.replace("test['source_sha256'] == hashlib.sha256(source).hexdigest()", "test['source_sha256'] == hashlib.sha256((P/'lynx-platform-errno-runtime.sh').read_bytes()).hexdigest()")
    validator=validator.replace("n.get('platform_classifier')", "n.get('errno_classifier')")
    insert="""    require((P/'lynx-platform-errno-runtime.sh').read_bytes() in source and (P/'lynx-live-ufs-name.sh').read_bytes() in source,'Errno control/name source missing')
    require(n['live_name_source_sha256']==hashlib.sha256((P/'lynx-live-ufs-name.sh').read_bytes()).hexdigest(),'Native live-name tested source differs')
    timing=sorted((ROOT/'tools/test-artifacts').glob('errno-timing-*/result.json'));require(timing,'Monotonic decoder test missing')
    t=json.loads(timing[-1].read_text());require(t['passed'] and t['decoder_sha256']==hashlib.sha256((ROOT/'tools/lynx_errno_timing.py').read_bytes()).hexdigest() and t['observer_sha256']==hashlib.sha256((ROOT/'tools/lynx_trial_observer.py').read_bytes()).hexdigest(),'Tested decoder/observer changed')
    manifest=json.loads((F/'build-validation.json').read_text());require(manifest['observation_seconds']==380 and manifest['timing_match_tolerance_seconds']==0.8 and manifest['baseline_reference_seconds']==21.9,'Timing protocol changed')
    require(manifest['target_delays_seconds']=={str(value):60+2*value for value in range(128)},'Timing field mapping changed')
"""
    marker="    out = P/'docs/platform-errno-image-validation.json'";assert validator.count(marker)==1
    validator=validator.replace(marker,insert+marker,1)
    save('validate_platform_errno_image.py',validator)
    trial=(T/'lynx_boot_a_platform_probe_trial.py').read_text().replace('busybox-platform-probe-v1','busybox-platform-errno-v1').replace(OLD,NEW)
    trial=trial.replace('validate_platform_probe_image.py','validate_platform_errno_image.py').replace('boot-a-platform-probe-trial-','boot-a-platform-errno-trial-')
    trial=trial.replace('from lynx_trial_observer import USBObserver','from lynx_trial_observer import USBObserver\nfrom lynx_errno_timing import decode_errno_timing')
    trial=trial.replace('up to 330 seconds','up to 380 seconds').replace('deadline=time.monotonic()+330','deadline=time.monotonic()+380')
    start=trial.index('            usb=json.loads(observer_path.read_text())');end=trial.index("\n        report['stock_undo_pending']",start)
    trial=trial[:start]+'''            usb=json.loads(observer_path.read_text())
            manifest=json.loads((LINUX.parent/'build-validation.json').read_text())
            report.update(decode_errno_timing(report['operations'][-1],usb,manifest))
'''+trial[end:]
    save('lynx_boot_a_platform_errno_trial.py',trial)
    print('Errno validation/monotonic trial tools prepared; no phone contacted.')


if __name__=='__main__':main()
