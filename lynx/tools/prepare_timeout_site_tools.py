"""Prepare a complementary log-context diagnostic, preserving every prior tool."""
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent;P=ROOT/'linux-port';T=ROOT/'tools'
def save(path,text):
    assert not path.exists(),str(path);path.write_text(text)
def main():
    tests=(T/'test_timeout_log_classifier.py').read_text()
    start=tests.index('    messages=');end=tests.index('    cases=[]',start)
    tests=tests[:start]+'''    messages=['ufshcd-mtk 112b0000.ufshci: probe failed -110',
              'scpsys: Failed to enable lp_clk ufs0(-110)',
              'ufshcd-mtk 112b0000.ufshci: Initialization failed',
              'ufshcd-mtk 112b0000.ufshci: ufshcd_init: variant mediatek init failed err -110',
              'ufshcd-mtk 112b0000.ufshci: regulator init failed -110',
              'ufshcd-mtk 112b0000.ufshci: ufshcd_setup_clocks: core_clk enable failed, err=-110']
    specs=[]
    for selection in range(64):
        raw='\\n'.join('[ 3.2][ T1] '+text for n,text in enumerate(messages) if selection & (1<<n))+'\\n'
        specs.append(('selection-'+str(selection),raw,selection))
    specs += [('unrelated','other-device: probe failed -110\\nscpsys: Failed to enable lp_clk gpu(-110)\\n',0),
              ('wrong-errno','scpsys: Failed to enable lp_clk ufs0(-5)\\n',0),
              ('power-clk-args','scpsys: Failed to enable clk ufs0(-110 1)\\n',2),
              ('cascaded',messages[0]+'\\n'+messages[2]+'\\n',5)]
'''+tests[end:]
    tests=tests.replace('lynx-classify-timeout-logs.awk','lynx-classify-timeout-sites.awk').replace('timeout-log-classifier-','timeout-site-classifier-')
    save(T/'test_timeout_site_classifier.py',tests)
    native=(T/'test_native_timeout_logs.py').read_text().replace('lynx-classify-timeout-logs.awk','lynx-classify-timeout-sites.awk').replace('timeout-log-classifier-','timeout-site-classifier-').replace('emulated-native-timeout-logs-','emulated-native-timeout-sites-')
    native=native.replace('LOG_KMSG_FIXTURE=33','LOG_KMSG_FIXTURE=2')
    save(T/'test_native_timeout_sites.py',native)
    control=(T/'test_timeout_log_control.py').read_text().replace('timeout-log-control-','timeout-site-control-').replace('timeout-log-classifier-','timeout-site-classifier-')
    # Runtime installed filename remains the same, fixture uses the new source.
    control=control.replace("str(P/'lynx-classify-timeout-logs.awk')","str(P/'lynx-classify-timeout-sites.awk')").replace("('health-two',33,","('health-two',2,")
    save(T/'test_timeout_site_control.py',control)
    builder=(P/'prepare_timeout_log_image.py').read_text().replace('busybox-timeout-log-v2','busybox-timeout-site-v1').replace("(P/'lynx-classify-timeout-logs.awk')","(P/'lynx-classify-timeout-sites.awk')")
    save(P/'prepare_timeout_site_image.py',builder)
    vm=(T/'test_timeout_log_image_vm.py').read_text().replace('busybox-timeout-log-v2','busybox-timeout-site-v1').replace('emulated-timeout-log-image-','emulated-timeout-site-image-')
    save(T/'test_timeout_site_image_vm.py',vm)
    decoder=(T/'lynx_timeout_log_timing.py').read_text();start=decoder.index('BITS=');end=decoder.index('\ndef decode_',start)
    decoder=decoder[:start]+'''BITS={1:'MediaTek UFS probe error -110',2:'ufs0 power-provider error -110',
      4:'UFS platform initialization error',8:'UFS variant initialization -110',
      16:'UFS regulator error',32:'UFS clock error'}
'''+decoder[end:]
    decoder=decoder.replace('decode_timeout_log_timing','decode_timeout_site_timing')
    save(T/'lynx_timeout_site_timing.py',decoder)
    timing=(T/'test_timeout_log_timing.py').read_text().replace('lynx_timeout_log_timing','lynx_timeout_site_timing').replace('decode_timeout_log_timing','decode_timeout_site_timing').replace('timeout-log-timing-','timeout-site-timing-').replace('busybox-timeout-log-v2','busybox-timeout-site-v1')
    save(T/'test_timeout_site_timing.py',timing)
    with (P/'.gitignore').open('a') as f:f.write('\nartifacts/busybox-timeout-site-*/\n')
    print('Complementary source/test tools prepared; no phone contacted.')
if __name__=='__main__':main()
