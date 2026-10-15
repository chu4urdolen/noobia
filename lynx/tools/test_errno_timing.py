"""Verify every timing field, rejected ambiguity and wall-clock jumps offline."""
import hashlib,json,tempfile,time
from pathlib import Path
from lynx_errno_timing import decode_errno_timing
from lynx_trial_observer import USBObserver

ROOT=Path(__file__).resolve().parent.parent


def main():
    out=ROOT/'tools/test-artifacts'/('errno-timing-'+str(time.time_ns()));out.mkdir()
    manifest=json.loads((ROOT/'linux-port/artifacts/busybox-platform-errno-v1/build-validation.json').read_text())
    operation={'started_monotonic':100.0,'elapsed_seconds':0.05,'finished_ns':1000000000000}
    def receipt(n,offset=0,jump=0):
        elapsed=manifest['baseline_reference_seconds']+60+2*n+offset
        return {'observation_complete':True,'fastboot_return_observed':True,'events':[{'monotonic_seconds':100.05+elapsed,
                'wall_time_ns':operation['finished_ns']+int((elapsed+jump)*1e9),'usb':[{'identifier':'0e8d:201c'}]}]}
    cases=[]
    for n in range(128):
        decoded=decode_errno_timing(operation,receipt(n),manifest)
        assert decoded['timing_nearest_code_hex']=='0x'+format(n,'02x') and decoded['timing_inferred_outcome'] is not None
        cases.append({'field':n,'accepted':True})
    for offset in [0.99,1.01,-0.99,-1.01]:
        decoded=decode_errno_timing(operation,receipt(19,offset),manifest);assert decoded['timing_inferred_outcome'] is None
    jumped=decode_errno_timing(operation,receipt(19,jump=60),manifest)
    assert jumped['timing_decoded_platform_return']==-19 and abs(jumped['wall_monotonic_disagreement_seconds']-60)<1e-6
    missing=receipt(19);del missing['events'][0]['monotonic_seconds']
    try:decode_errno_timing(operation,missing,manifest)
    except KeyError:pass
    else:raise AssertionError('Must not silently fall back to wall clock')
    observer=USBObserver(out/'observer.json')
    observer.record([{'identifier':'0e8d:201c'}]);observer.record([]);observer.record([{'identifier':'0e8d:201c'}]);observer.finished=True;observer.save()
    saved=json.loads((out/'observer.json').read_text())
    assert saved['started_monotonic']>0 and saved['fastboot_return_observed'] and all('monotonic_seconds' in event for event in saved['events'])
    report={'passed':True,'fields':cases,'ambiguous_returns_rejected':4,'wall_clock_jump_preserved_errno':True,
            'missing_monotonic_refused':True,'observer_monotonic_fields_verified':True,'phone_contacted':False,
            'decoder_sha256':hashlib.sha256((ROOT/'tools/lynx_errno_timing.py').read_bytes()).hexdigest(),
            'observer_sha256':hashlib.sha256((ROOT/'tools/lynx_trial_observer.py').read_bytes()).hexdigest()}
    path=out/'result.json';path.write_text(json.dumps(report,indent=2)+'\n');print(path)


if __name__=='__main__':main()
