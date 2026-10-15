"""Prepare separate clock-helper supervisor, guard, timing and trial tools."""
from pathlib import Path
R=Path(__file__).resolve().parent.parent;T=R/'tools'
SHA='b161edddb4a1a6a2e572f16298397f162d14f2d3e888220e58b576c5c4c0fe76'
def save(name,source):
    out=T/name;assert not out.exists(),out;compile(source,str(out),'exec');out.write_text(source)
def main():
    source=(T/'test_ufs_trace_probe_control.py').read_text().replace('lynx-ufs-trace-probe-runtime.sh','lynx-stock-clock-helper-probe-runtime.sh').replace('ufs-trace-probe-control-','stock-clock-helper-probe-control-')
    source=source.replace("('clear-fail',9)]", "('clear-fail',9),('helper-refused',10),('helper-insertion-failed',11),('helper-binding-failed',12),('helper-counters-failed',13)]")
    source=source.replace('functions="lynx_diag_init()', 'functions="lynx_stock_clock_helper_load() { return "+str(expected if expected>=10 else 0)+"; }\\nlynx_diag_init()')
    save('test_stock_clock_helper_probe_control.py',source)
    source=(T/'test_refclk_v2_probe_image_guard.py').read_text().replace('busybox-refclk-trace-probe-v2','busybox-stock-clock-helper-probe-v1').replace('emulated-refclk-v2-probe-guard-','emulated-stock-clock-helper-probe-guard-')
    save('test_stock_clock_helper_probe_image_guard.py',source)
    source=(T/'lynx_ufs_trace_probe_timing.py').read_text().replace('range(10)','range(14)');save('lynx_stock_clock_helper_probe_timing.py',source)
    source=(T/'test_ufs_trace_probe_timing.py').read_text().replace('lynx_ufs_trace_probe_timing','lynx_stock_clock_helper_probe_timing').replace('busybox-ufs-trace-probe-v1','busybox-stock-clock-helper-probe-v1').replace('range(10)','range(14)').replace('range(9)','range(13)').replace('baseline+180','baseline+210').replace('ufs-trace-probe-timing-test','stock-clock-helper-probe-timing-test')
    save('test_stock_clock_helper_probe_timing.py',source)
    source=(T/'lynx_boot_a_refclk_v2_probe_trial.py').read_text().replace('busybox-refclk-trace-probe-v2','busybox-stock-clock-helper-probe-v1').replace('b4a505426c91b3a0c151b977ddcfbfddeabcca612a59959408230c19d317aea1',SHA).replace('validate_refclk_v2_probe_image','validate_stock_clock_helper_probe_image').replace('boot-a-refclk-v2-probe-trial-','boot-a-stock-clock-helper-probe-trial-').replace('lynx_ufs_trace_probe_timing','lynx_stock_clock_helper_probe_timing').replace('nine audited reference-clock checkpoints armed','audited stock clock startup helper and nine reference-clock checkpoints armed')
    save('lynx_boot_a_stock_clock_helper_probe_trial.py',source)
    print('Separate stock clock helper control/guard/timing/trial tools prepared; no phone contacted.')
if __name__=='__main__':main()
