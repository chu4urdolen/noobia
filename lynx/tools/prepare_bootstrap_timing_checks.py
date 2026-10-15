"""Prepare pinned guard and boot_a trial tools without overwriting earlier tools."""
from pathlib import Path
R=Path(__file__).resolve().parent.parent;T=R/'tools'
OLD='4eec20add7e57d70c5f29b11f02b7f726e8cc8ff24be1395aa738605c39bccf5';NEW='a9c233c6aefbae80e2e9cd1fabbb1dcda8cdac3119d9ea58bc5e95b73c96802a'
def main():
    s=(T/'test_retained_refclk_guard.py').read_text().replace('busybox-retained-refclk-trace-query-v1','busybox-bootstrap-timing-v1').replace('emulated-retained-refclk-trace-guard-','emulated-bootstrap-timing-guard-')
    p=T/'test_bootstrap_timing_guard.py';assert not p.exists();p.write_text(s)
    s=(T/'lynx_boot_a_retained_refclk_trial.py').read_text().replace(OLD,NEW).replace('busybox-retained-refclk-trace-query-v1','busybox-bootstrap-timing-v1').replace('lynx_retained_ufs_trace_timing','lynx_bootstrap_timing').replace('validate_retained_refclk_image','validate_bootstrap_timing_image').replace('boot-a-retained-refclk-trial-','boot-a-bootstrap-timing-trial-').replace('main UFS insertion, payload and radio excluded','guarded stock UFS plus read-only own boot_a payload; radio excluded')
    p=T/'lynx_boot_a_bootstrap_timing_trial.py';assert not p.exists();p.write_text(s)
    print('Pinned guard and trial tools prepared.')
if __name__=='__main__':main()
