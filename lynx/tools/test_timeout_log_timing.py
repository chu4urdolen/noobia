import hashlib,json,time
from pathlib import Path
from lynx_timeout_log_timing import decode_timeout_log_timing,BITS
ROOT=Path(__file__).resolve().parent.parent
def main():
    manifest=json.loads((ROOT/'linux-port/artifacts/busybox-timeout-log-v2/build-validation.json').read_text())
    cases=[]
    for code in range(128):
        elapsed=21.9+60+2*code
        operation={'started_monotonic':100,'elapsed_seconds':1,'finished_ns':1000000000}
        usb={'observation_complete':True,'fastboot_return_observed':True,'events':[{'usb':[{'identifier':'0e8d:201c'}],'monotonic_seconds':101+elapsed,'wall_time_ns':int(1e9+elapsed*1e9)}]}
        result=decode_timeout_log_timing(operation,usb,manifest)
        assert 'timing_decoded_platform_return' not in result
        assert result['timing_kernel_log_mask']==(code if code<64 else None)
        assert result['timing_kernel_log_indications']==([text for bit,text in BITS.items() if code & bit] if code<64 else [])
        if 64<=code<124:assert result['timing_inferred_outcome'] is None
        cases.append(code)
    out=ROOT/'tools/test-artifacts'/('timeout-log-timing-'+str(time.time_ns()));out.mkdir()
    path=out/'result.json';path.write_text(json.dumps({'passed':True,'cases':cases,'decoder_sha256':hashlib.sha256((ROOT/'tools/lynx_timeout_log_timing.py').read_bytes()).hexdigest(),'phone_contacted':False},indent=2)+'\n');print(path)
if __name__=='__main__':main()
