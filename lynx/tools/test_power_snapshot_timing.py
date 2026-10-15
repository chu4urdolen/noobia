"""Verify metadata bitmasks and reserved/impossible values on the timing grid."""
import hashlib,json
from pathlib import Path
from lynx_progress_timing import decode_progress_timing
R=Path(__file__).resolve().parent.parent;P=R/'linux-port';m=json.loads((P/'artifacts/busybox-power-metadata-snapshot-v1/build-validation.json').read_text());base=21.83350131
def run(delay):
    elapsed=base+delay;op={'started_monotonic':10,'elapsed_seconds':.1,'finished_ns':1000000000};usb={'observation_complete':True,'fastboot_return_observed':True,'events':[{'monotonic_seconds':10.1+elapsed,'wall_time_ns':int(1000000000+elapsed*1e9),'usb':[{'identifier':'0e8d:201c'}]}]}
    return decode_progress_timing(op,usb,m,base)
cases=[]
for code in [0,1,4,5,6,7,8,9,12,13,14,15,16,17,18,125,127]:
    for error in [-.2,0,.2]:
        result=run(120+2*code+error);assert result['timing_module_progress_field']==code,result
        cases.append({'code':code,'error':error})
for delay in [124,126,140,142,158,121,123,151,155]:
    result=run(delay);assert result['timing_module_progress_field'] is None and result['timing_inferred_outcome'] is None,result
report={'passed':True,'cases':cases,'reserved_or_midpoint_delays_rejected':9,'phone_contacted':False,'decoder_sha256':hashlib.sha256((R/'tools/lynx_progress_timing.py').read_bytes()).hexdigest()}
out=P/'docs/power-snapshot-timing-test.json';out.write_text(json.dumps(report,indent=2)+'\n');print(out)
