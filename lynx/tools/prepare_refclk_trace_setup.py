"""Prepare standard offset probes only at audited stock instruction boundaries."""
import json
from pathlib import Path
R=Path(__file__).resolve().parent.parent;P=R/'linux-port'
def main():
    audit=json.loads((P/'docs/stock-ufs-refclk-audit.json').read_text())
    assert audit['module_sha256']=='31e452411297a57a6ed4c31b207c3b4604fa8b55acd95cff6135c680846614a4'
    function=next(r for r in audit['functions'] if r['function']['name']=='ufs_mtk_setup_ref_clk')
    instructions={r['offset']:r for r in function['instructions']}
    expected={0x88:'bl',0x8c:'dmb',0xa0:'str',0xa4:'b',0xf0:'ldr',0xf4:'nop'}
    assert all(instructions[n]['mnemonic']==name for n,name in expected.items())
    assert instructions[0x88]['relocation']['symbol']=='__arm_smccc_smc'
    source=(P/'ufs-persistent-trace-setup.sh').read_text()
    start=source.index('    for ufs_trace_symbol in ');end=source.index('    log "UFS_PERSISTENT_TRACE_READY',start)
    replacement='''    for ufs_trace_item in p:ufs_mediatek_mod:ufs_mtk_setup_ref_clk p:ufs_mediatek_mod:ufs_mtk_setup_ref_clk+0x88 p:ufs_mediatek_mod:ufs_mtk_setup_ref_clk+0x8c p:ufs_mediatek_mod:ufs_mtk_setup_ref_clk+0xa0 p:ufs_mediatek_mod:ufs_mtk_setup_ref_clk+0xa4 p:ufs_mediatek_mod:ufs_mtk_setup_ref_clk+0xf0 p:ufs_mediatek_mod:ufs_mtk_setup_ref_clk+0xf4 r32:ufs_mediatek_mod:ufs_mtk_setup_ref_clk p:ufs_mediatek_mod:ufs_mtk_boost_crypt; do
        ufs_trace_index=$((ufs_trace_index+1))
        ufs_trace_kind=${ufs_trace_item%%:*}
        ufs_trace_symbol=${ufs_trace_item#*:}
        ufs_trace_event="lx${ufs_trace_token}_${ufs_trace_index}"
        ufs_trace_args=''
        case "$ufs_trace_index" in
            1) ufs_trace_args=' on=$arg2:u8' ;;
            8) ufs_trace_args=' ret=$retval:s32' ;;
        esac
        printf '%s\\n' "$ufs_trace_kind:lynx_ufs/$ufs_trace_event $ufs_trace_symbol$ufs_trace_args" >> /run/lynx/trace/kprobe_events || return 1
        $BB dd if=/run/lynx/trace-enable of="/run/lynx/trace/events/lynx_ufs/$ufs_trace_event/enable" bs=2 count=1 || return 1
        ufs_trace_enabled=$($BB cat "/run/lynx/trace/events/lynx_ufs/$ufs_trace_event/enable") || return 1
        [ "$ufs_trace_enabled" = 1 ] || return 1
    done
'''
    source=source[:start]+replacement+source[end:]
    path=P/'ufs-refclk-persistent-trace-setup.sh';assert not path.exists();path.write_text(source)
    print(path)
if __name__=='__main__':main()
