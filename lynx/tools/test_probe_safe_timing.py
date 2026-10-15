"""Check both reset timing grids and reject overlapping interpretations."""
import hashlib,json
from pathlib import Path
from lynx_probe_safe_timing import decode_progress_timing
R=Path(__file__).resolve().parent.parent;P=R/'linux-port';manifest=json.loads((P/'artifacts/busybox-ufs-probe-emergency-v1/build-validation.json').read_text());baseline=21.83350131
def run(code,offset,error):
    elapsed=baseline+120+2*code+offset+error
    op={'started_monotonic':10,'elapsed_seconds':.01,'finished_ns':1000000000}
    usb={'observation_complete':True,'fastboot_return_observed':True,'events':[{'monotonic_seconds':10.01+elapsed,'wall_time_ns':int(1000000000+elapsed*1e9),'usb':[{'identifier':'0e8d:201c'}]}]}
    return decode_progress_timing(op,usb,manifest,baseline)
cases=[]
for code in [0,1,35,40,41,85,125,127]:
    for offset,path in [(0,'ordinary'),(5,'emergency-candidate')]:
        for error in [-.15,0,.15]:
            result=run(code,offset,error)
            assert result['timing_module_progress_field']==code and result['reset_path']==path,(code,offset,error,result)
            cases.append({'code':code,'offset':offset,'error':error,'unique':True})
for code,offset,error in [(41,0,-.5),(41,5,.5)]:
    result=run(code,offset,error)
    assert result['timing_inferred_outcome'] is None and len(result['timing_interpretations'])>1,result
report={'passed':True,'cases':cases,'overlapping_grids_rejected':2,'phone_contacted':False,'decoder_sha256':hashlib.sha256((R/'tools/lynx_probe_safe_timing.py').read_bytes()).hexdigest()}
out=P/'docs/probe-safe-timing-test.json';out.write_text(json.dumps(report,indent=2)+'\n');print(out)
