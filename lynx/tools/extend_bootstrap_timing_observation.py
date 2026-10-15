"""Extend a live bootstrap timing trial's passive observer without phone commands."""
import hashlib,json,time
from pathlib import Path
from lynx_trial_observer import USBObserver
from lynx_bootstrap_timing import decode_progress_timing
R=Path(__file__).resolve().parent.parent
TRIAL=R/'logs/boot-a-bootstrap-timing-trial-1792009047412492624.json'
IMAGE='a9c233c6aefbae80e2e9cd1fabbb1dcda8cdac3119d9ea58bc5e95b73c96802a'
def main():
    trial=json.loads(TRIAL.read_text())
    assert trial['mode']=='flash-linux' and trial['authorized_partition']=='boot_a'
    op=trial['operations'][-1];assert op['command'][3:]==['reboot'] and op['exit_code']==0
    assert any(i['sha256']==IMAGE for i in trial['images'])
    source=Path(trial['usb_observer_receipt']);raw=source.read_bytes();prior=json.loads(raw)
    assert prior['error'] is None and prior['initial_fastboot_seen'] and prior['departure_observed']
    assert not prior['fastboot_return_observed']
    assert (time.time_ns()-prior['heartbeat_ns'])/1e9<3
    stamp=str(time.time_ns());out=R/'logs'/('bootstrap-timing-observer-extension-'+stamp+'.json')
    observer=USBObserver(R/'logs'/('usb-bootstrap-extended-'+stamp+'.json'))
    observer.started=prior['started_monotonic'];observer.started_ns=prior['started_ns']
    observer.events=prior['events'];observer.seen_fastboot=True;observer.departed=True
    report={'phone_commands_sent':False,'source_trial':str(TRIAL),'source_observer':str(source),'seed_observer_sha256':hashlib.sha256(raw).hexdigest(),'resume_ns':time.time_ns(),'seed_heartbeat_ns':prior['heartbeat_ns'],'observer_receipt':str(observer.output),'state':'observing','deadline_seconds_after_reboot':360,'limits':'Inherited real prior USB events, then passive sysfs observation. Separate receipt; original270s observer retained. Requires normal reset evidence and physical non-interference.'}
    out.write_text(json.dumps(report,indent=2)+'\n')
    observer.start()
    deadline=op['started_monotonic']+op['elapsed_seconds']+360
    while time.monotonic()<deadline and not observer.returned.is_set():
        if observer.failure:raise RuntimeError(observer.failure)
        time.sleep(.25)
    observer.stop()
    report.update(state='completed',fastboot_return_observed=observer.returned.is_set(),completed_ns=time.time_ns())
    if observer.returned.is_set():
        manifest=json.loads((R/'linux-port/artifacts/busybox-bootstrap-timing-v1/build-validation.json').read_text())
        baseline=json.loads((R/'linux-port/docs/progress-debug-calibration.json').read_text())['baseline_seconds']
        report.update(decode_progress_timing(op,json.loads(observer.output.read_text()),manifest,baseline))
    out.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'receipt':str(out),**report},indent=2))
if __name__=='__main__':main()
