"""Derive pinned guard and trial harnesses for the corrected trace-only change."""
from pathlib import Path
R=Path(__file__).resolve().parent.parent;T=R/'tools'
SHA='b4a505426c91b3a0c151b977ddcfbfddeabcca612a59959408230c19d317aea1'
def save(name,source):
    out=T/name;assert not out.exists(),out;compile(source,str(out),'exec');out.write_text(source)
def main():
    source=(T/'test_ufs_trace_probe_image_guard.py').read_text().replace('busybox-ufs-trace-probe-v1','busybox-refclk-trace-probe-v2').replace('emulated-ufs-trace-probe-guard-','emulated-refclk-v2-probe-guard-')
    save('test_refclk_v2_probe_image_guard.py',source)
    source=(T/'lynx_boot_a_ufs_trace_probe_trial.py').read_text().replace('busybox-ufs-trace-probe-v1','busybox-refclk-trace-probe-v2').replace('30a2757ef742a859a24d577b35bf33111c3ed3cc5d43baa4199cf0d889f363ff',SHA).replace('validate_ufs_trace_probe_image','validate_refclk_v2_probe_image').replace('boot-a-ufs-trace-probe-trial-','boot-a-refclk-v2-probe-trial-').replace('nine trace events armed','nine audited reference-clock checkpoints armed')
    save('lynx_boot_a_refclk_v2_probe_trial.py',source)
    print('Pinned v2 guard/trial tools prepared; no phone contacted.')
if __name__=='__main__':main()
