"""Check slot boundaries, offsets, and rejection of incomplete observations."""
import json
from pathlib import Path
from lynx_stock_clock_helper_probe_timing import decode_progress_timing
R=Path(__file__).resolve().parent.parent
def main():
    manifest=json.loads((R/'linux-port/artifacts/busybox-stock-clock-helper-probe-v1/build-validation.json').read_text())
    baseline=21.833501310
    operation=dict(started_monotonic=100,elapsed_seconds=1,finished_ns=101000000000)
    def check(delay):
        event=dict(monotonic_seconds=101+delay,wall_time_ns=int((101+delay)*1e9),usb=[dict(identifier='0e8d:201c')])
        return decode_progress_timing(operation,dict(observation_complete=True,fastboot_return_observed=True,events=[event]),manifest,baseline)
    tests=0
    for code in range(14):
        for offset in [-1.8,0,1.8]:
            result=check(baseline+120+5*code+offset)
            assert result['timing_module_progress_field']==code
            tests+=1
    for code in range(13):
        assert check(baseline+122.5+5*code)['timing_module_progress_field'] is None
        tests+=1
    for delay in [baseline+100,baseline+210]:
        assert check(delay)['timing_module_progress_field'] is None
        tests+=1
    report=dict(passed=True,cases=tests,phone_contacted=False,limits='Timing geometry only; does not validate physical startup drift or reset source.')
    out=R/'linux-port/docs/stock-clock-helper-probe-timing-test.json';out.write_text(json.dumps(report,indent=2)+'\n');print(out)
if __name__=='__main__':main()
