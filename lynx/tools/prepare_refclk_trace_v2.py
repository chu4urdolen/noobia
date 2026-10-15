"""Preserve rejected v1; move after-read probe past the dynamic branch site."""
import json
from pathlib import Path
R=Path(__file__).resolve().parent.parent;P=R/'linux-port';T=R/'tools'
def save(path,source):
    assert not path.exists(),path
    if path.suffix=='.py':compile(source,str(path),'exec')
    path.write_text(source)
def main():
    audit=json.loads((P/'docs/stock-ufs-refclk-audit.json').read_text())
    row=next(x for x in audit['functions'] if x['function']['name']=='ufs_mtk_setup_ref_clk')
    assert next(x for x in row['instructions'] if x['offset']==0xf8)['mnemonic']=='dmb'
    source=(P/'ufs-refclk-persistent-trace-setup.sh').read_text();assert source.count('ufs_mtk_setup_ref_clk+0xf4')==1
    save(P/'ufs-refclk-persistent-trace-v2-setup.sh',source.replace('ufs_mtk_setup_ref_clk+0xf4','ufs_mtk_setup_ref_clk+0xf8'))
    source=(T/'test_native_refclk_trace.py').read_text().replace('ufs-refclk-persistent-trace-setup.sh','ufs-refclk-persistent-trace-v2-setup.sh').replace('emulated-native-refclk-trace-','emulated-native-refclk-trace-v2-')
    save(T/'test_native_refclk_trace_v2.py',source)
    source=(T/'test_refclk_controlled_probe.py').read_text().replace('ufs-refclk-persistent-trace-setup.sh','ufs-refclk-persistent-trace-v2-setup.sh').replace('refclk-controlled-probe-','refclk-v2-controlled-probe-')
    save(T/'test_refclk_v2_controlled_probe.py',source)
    source=(P/'prepare_refclk_trace_probe_image.py').read_text().replace('busybox-refclk-trace-probe-v1','busybox-refclk-trace-probe-v2').replace('ufs-refclk-persistent-trace-setup.sh','ufs-refclk-persistent-trace-v2-setup.sh').replace('(+0xf4)','(+0xf8)')
    save(P/'prepare_refclk_trace_probe_v2_image.py',source)
    print('v1 retained unflashed; v2 after-read point now+0xf8, native validation required.')
if __name__=='__main__':main()
