"""Separate pinned readback tools; preserve old query tests and interpretations."""
from pathlib import Path
R=Path(__file__).resolve().parent.parent;T=R/'tools'
OLD='299c1ab3207e48d546077506690a1cfb91bdf05d0fe2c63d3a56dc4feff5ef75';NEW='4eec20add7e57d70c5f29b11f02b7f726e8cc8ff24be1395aa738605c39bccf5'
def save(name,source):
    out=T/name;assert not out.exists(),out;compile(source,str(out),'exec');out.write_text(source)
def common(source):
    return source.replace(OLD,NEW).replace('busybox-retained-ufs-trace-query-v1','busybox-retained-refclk-trace-query-v1')
def main():
    source=common((T/'test_retained_ufs_trace_control.py').read_text()).replace('retained-ufs-trace-control-','retained-refclk-trace-control-');save('test_retained_refclk_control.py',source)
    source=common((T/'test_native_retained_ufs_trace.py').read_text()).replace('emulated-native-retained-ufs-trace-','emulated-native-retained-refclk-trace-');save('test_native_retained_refclk.py',source)
    source=common((T/'test_retained_ufs_trace_guard.py').read_text()).replace('emulated-retained-ufs-trace-guard-','emulated-retained-refclk-trace-guard-');save('test_retained_refclk_guard.py',source)
    source=common((T/'validate_retained_ufs_trace_image.py').read_text()).replace('busybox-ufs-trace-probe-v1','busybox-refclk-trace-probe-v2').replace('30a2757ef742a859a24d577b35bf33111c3ed3cc5d43baa4199cf0d889f363ff','b4a505426c91b3a0c151b977ddcfbfddeabcca612a59959408230c19d317aea1')
    start=source.index("    names=['ufs_mtk_probe'");end=source.index('\n    require(reference_manifest',start)
    labels=['ufs_mtk_setup_ref_clk entry','before firmware call (+0x88)','after firmware call (+0x8c)','before request register store (+0xa0)','after request register store (+0xa4)','before acknowledgement register read (+0xf0)','after acknowledgement register read (+0xf8)','ufs_mtk_setup_ref_clk returned','ufs_mtk_boost_crypt entry']
    source=source[:start]+'    names='+repr(labels)+source[end:]
    source=source.replace("'last reference trace entry in selected record: '+name+('; generic core event may concern another device' if i>=7 else '; entry does not prove return')", "'last retained reference checkpoint: '+name+('; return marker retained, retval not retrieved' if i==8 else '; marker brackets execution, not exact stop')")
    source=source.replace('retained-ufs-trace-control-','retained-refclk-trace-control-').replace('emulated-native-retained-ufs-trace-','emulated-native-retained-refclk-trace-').replace('emulated-retained-ufs-trace-guard-','emulated-retained-refclk-trace-guard-').replace('retained-ufs-trace-validation','retained-refclk-validation')
    save('validate_retained_refclk_image.py',source)
    source=common((T/'lynx_boot_a_retained_ufs_trace_trial.py').read_text()).replace('validate_retained_ufs_trace_image','validate_retained_refclk_image').replace('boot-a-retained-ufs-trace-trial-','boot-a-retained-refclk-trial-');save('lynx_boot_a_retained_refclk_trial.py',source)
    print('Finer checkpoint readback tools prepared; no phone contacted.')
if __name__=='__main__':main()
