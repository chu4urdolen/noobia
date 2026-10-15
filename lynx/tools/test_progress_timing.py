import hashlib,json,time
from pathlib import Path
from lynx_progress_timing import decode_progress_timing
ROOT=Path(__file__).resolve().parent.parent
def frame(elapsed):
    operation={'started_monotonic':100,'elapsed_seconds':1,'finished_ns':1000000000}
    usb={'observation_complete':True,'fastboot_return_observed':True,'events':[{'usb':[{'identifier':'0e8d:201c'}],'monotonic_seconds':101+elapsed,'wall_time_ns':int(1e9+elapsed*1e9)}]}
    return operation,usb
def main():
    P=ROOT/'linux-port';manifest=json.loads((P/'artifacts/busybox-module-progress-debug-28-v1/build-validation.json').read_text());base=json.loads((P/'artifacts/busybox-module-progress-debug-0-v1/build-validation.json').read_text())
    for code in range(128):
        op,usb=frame(21.9+120+2*code);result=decode_progress_timing(op,usb,manifest,21.9)
        valid=not manifest['result_codes'][str(code)].startswith('reserved')
        assert result['timing_module_progress_field']==(code if valid else None),code
    for code in [0,28,68,108]:
        op,usb=frame(21.9+120+2*code+1);assert decode_progress_timing(op,usb,manifest,21.9)['timing_module_progress_field'] is None
    op,usb=frame(141.9);calibration=decode_progress_timing(op,usb,base);assert calibration['baseline_range_plausible'] and abs(calibration['timing_baseline_candidate_seconds']-21.9)<1e-8
    for elapsed in [54,180]:
        op,usb=frame(elapsed);assert not decode_progress_timing(op,usb,base)['baseline_range_plausible']
    out=ROOT/'tools/test-artifacts'/('module-progress-timing-'+str(time.time_ns()));out.mkdir()
    path=out/'result.json';path.write_text(json.dumps({'passed':True,'fields_tested':128,'midpoints_rejected':4,'calibration_range_checked':True,'decoder_sha256':hashlib.sha256((ROOT/'tools/lynx_progress_timing.py').read_bytes()).hexdigest(),'phone_contacted':False},indent=2)+'\n');print(path)
if __name__=='__main__':main()
