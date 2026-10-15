"""Verify widened timing, old-profile-sized drift and reserved/midpoint rejection."""
import hashlib,json
from pathlib import Path
from lynx_power_snapshot_v2_timing import decode_progress_timing
R=Path(__file__).resolve().parent.parent;P=R/'linux-port';m=json.loads((P/'artifacts/busybox-power-metadata-snapshot-v2/build-validation.json').read_text());base=21.83350131
def run(delay):
    elapsed=base+delay;op={'started_monotonic':10,'elapsed_seconds':.1,'finished_ns':1000000000};usb={'observation_complete':True,'fastboot_return_observed':True,'events':[{'monotonic_seconds':10.1+elapsed,'wall_time_ns':int(1000000000+elapsed*1e9),'usb':[{'identifier':'0e8d:201c'}]}]}
    return decode_progress_timing(op,usb,m,base)
cases=[]
for code,text in m['result_codes'].items():
    n=int(code)
    if text.startswith('reserved'):continue
    for error in [-1.8,-1.5255,0,1.5255,1.8]:
        result=run(120+5*n+error);assert result['timing_module_progress_field']==n,result
        cases.append({'code':n,'error':error})
for delay in [130,135,170,175,212.5,227.5,452.5]:
    result=run(delay);assert result['timing_module_progress_field'] is None and result['timing_inferred_outcome'] is None,result
report={'passed':True,'cases':cases,'reserved_or_midpoint_delays_rejected':7,'phone_contacted':False,'decoder_sha256':hashlib.sha256((R/'tools/lynx_power_snapshot_v2_timing.py').read_bytes()).hexdigest()}
out=P/'docs/power-snapshot-v2-timing-test.json';out.write_text(json.dumps(report,indent=2)+'\n');print(out)
