"""Observe matching and setup; never replace a return value or force binding."""
from pathlib import Path
import argparse

P=Path(__file__).resolve().parent.parent/'linux-port'


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--v2',action='store_true');args=parser.parse_args()
    header=(P/'docs/wifi-source-reference/device-driver.h').read_text()
    assert 'struct device_driver {\n\tconst char\t\t*name;' in header,'Verify the name field before fetching it'
    source=(P/'lynx-driver-trace-core-v1.sh').read_text()
    marker="    printf '256\\n' >";assert source.count(marker)==1
    events='''    printf '%s\\n' 'p:lynx_ufs/match_enter platform_match name=+0(+0($arg1)):string driver=+0($arg2):string' >> "$trace_root/kprobe_events" || return 1
    printf '%s\\n' 'r32:lynx_ufs/match_return platform_match ret=$retval:s32' >> "$trace_root/kprobe_events" || return 1
    printf '%s\\n' 'p:lynx_ufs/dma_enter platform_dma_configure name=+0(+0($arg1)):string' >> "$trace_root/kprobe_events" || return 1
    printf '%s\\n' 'r32:lynx_ufs/dma_return platform_dma_configure ret=$retval:s32' >> "$trace_root/kprobe_events" || return 1
    printf '%s\\n' 'p:lynx_ufs/platform_enter platform_drv_probe name=+0(+0($arg1)):string' >> "$trace_root/kprobe_events" || return 1
    printf '%s\\n' 'r32:lynx_ufs/platform_return platform_drv_probe ret=$retval:s32' >> "$trace_root/kprobe_events" || return 1
'''
    source=source.replace(marker,events+marker.replace('256','4096'),1)
    source=source.replace('pins_enter pins_return;','pins_enter pins_return match_enter match_return dma_enter dma_return platform_enter platform_return;',1)
    marker="    printf '0\\n' > \"$trace_instance/tracing_on\" || return 1\n";assert source.count(marker)==1
    source=source.replace(marker,"    $BB sh -c 'echo $$' > /run/lynx/trace-health-pid || return 1\n"+marker,1)
    if args.v2:
        assert source.count('driver=+0($arg2):string')==1
        source=source.replace('driver=+0($arg2):string','driver=+0(+0($arg2)):string',1)
    path=P/('lynx-driver-trace-platform-v2.sh' if args.v2 else 'lynx-driver-trace-platform-v1.sh');assert not path.exists(),'Preserve prior collector';path.write_text(source);print(path)


if __name__=='__main__':main()
