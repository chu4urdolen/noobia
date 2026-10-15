"""Check calibrated interface statuses and reject half-step/unknown timings."""
import hashlib,json
from pathlib import Path
from lynx_reset_interface_timing import decode_progress_timing
R=Path(__file__).resolve().parent.parent;P=R/'linux-port';m=json.loads((P/'artifacts/busybox-reset-interface-v1/build-validation.json').read_text());base=21.83350131
def run(delay):
    elapsed=base+delay
    op={'started_monotonic':10,'elapsed_seconds':.1,'finished_ns':1000000000}
    usb={'observation_complete':True,'fastboot_return_observed':True,'events':[{'monotonic_seconds':10.1+elapsed,'wall_time_ns':int(1000000000+elapsed*1e9),'usb':[{'identifier':'0e8d:201c'}]}]}
    return decode_progress_timing(op,usb,m,base)
cases=[]
for code in [0,1,2,3,125,127]:
    for error in [-.2,0,.2]:
        result=run(120+2*code+error);assert result['reset_interface_presence_field']==code,result
        cases.append({'code':code,'error':error})
for delay in [121,123,125,130,371,373]:
    result=run(delay);assert result['reset_interface_presence_field'] is None and result['timing_inferred_outcome'] is None,result
report={'passed':True,'cases':cases,'unclassified_delays':6,'phone_contacted':False,'decoder_sha256':hashlib.sha256((R/'tools/lynx_reset_interface_timing.py').read_bytes()).hexdigest()}
out=P/'docs/reset-interface-timing-test.json';out.write_text(json.dumps(report,indent=2)+'\n');print(out)
