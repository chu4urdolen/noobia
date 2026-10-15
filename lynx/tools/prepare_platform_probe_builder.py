"""Preserve earlier candidates and prepare the platform-chain diagnostic."""
from pathlib import Path

P=Path(__file__).resolve().parent.parent/'linux-port'


def main():
    source=(P/'prepare_core_probe_image.py').read_text()
    source=source.replace("F=P/'artifacts/busybox-probe-trace-v3'","F=P/'artifacts/busybox-core-probe-v1'")
    source=source.replace("OUT=P/'artifacts/busybox-core-probe-v1'","OUT=P/'artifacts/busybox-platform-probe-v1'")
    source=source.replace('b8114a11af588a9f40df0ab125895388a567879a913a973186aacc764b2185b4','dbc47af2604563013d2e7591c81b788551938d4467aeedad131370c4ae4eb94f')
    source=source.replace('lynx-driver-trace-core-v1.sh','lynx-driver-trace-platform-v2.sh').replace('lynx-classify-core-trace.awk','lynx-classify-platform-trace.awk')
    source=source.replace("start=runtime.index(b'        probe_code=3\\n')","start=runtime.index(b'        probe_code=1\\n')")
    source=source.replace('trace_supplier_ret trace_pins_ret trace_domain_ret trace_mtk_ret','trace_match_ret trace_dma_ret trace_platform_ret trace_health_count')
    source=source.replace('CORE_CLASSIFIED code=$probe_code supplier=$trace_supplier_ret pins=$trace_pins_ret domain=$trace_domain_ret mtk=$trace_mtk_ret','PLATFORM_CLASSIFIED code=$probe_code match=$trace_match_ret dma=$trace_dma_ret platform=$trace_platform_ret health=$trace_health_count')
    start=source.index("                  result_codes={");end=source.index("    (OUT/'build-validation.json')",start)
    source=source[:start]+'''                  result_codes={'1':'trace health/capture/correlation unavailable',
                                '2':'last UFS match with expected driver returned zero or negative',
                                '3':'last matched UFS DMA configure returned nonzero',
                                '4':'last matched UFS platform probe wrapper returned nonzero',
                                '5':'healthy tracing but no completed expected UFS driver match recorded',
                                '6':'expected UFS driver matched; no completed platform probe wrapper recorded',
                                '7':'last matched UFS platform probe wrapper returned zero',
                                '8':'bootstrap worker exceeded 180 second deadline'})
'''+source[end:]
    path=P/'prepare_platform_probe_image.py';assert not path.exists(),'Preserve prior builders';path.write_text(source);print(path)


if __name__=='__main__':main()
