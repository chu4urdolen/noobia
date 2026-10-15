"""Prepare one-new-module checkpoint and independent stock initcall test."""
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent;P=ROOT/'linux-port';T=ROOT/'tools'
def save(path,raw):
    assert not path.exists();path.write_text(raw)
def main():
    runtime=(P/'lynx-module-progress-runtime.sh').read_text()
    runtime=runtime.replace('    lynx_progress_clock || return 1\n    progress_started=', '''    IFS=' ' read -r progress_expected < /etc/lynx/progress-count || return 1
    case "$progress_expected" in 28|29|30|31|32) ;; *) return 1 ;; esac
    lynx_progress_clock || return 1
    progress_started=''',1)
    runtime=runtime.replace('"$progress_index" -le 32','"$progress_index" -le "$progress_expected"').replace('"$progress_index" = 32','"$progress_index" = "$progress_expected"').replace('lynx_progress_write 113','lynx_progress_write 0').replace('PROGRESS_PREFIX_INSERTIONS_COMPLETED','PROGRESS_SELECTED_PREFIX_INSERTIONS_COMPLETED')
    save(P/'lynx-module-progress-v2-runtime.sh',runtime)
    builder=(P/'prepare_module_progress_image.py').read_text().replace('busybox-module-progress-v1','busybox-module-progress-v2').replace('lynx-module-progress-runtime.sh','lynx-module-progress-v2-runtime.sh')
    builder=builder.replace("prefix=modules[:modules.index('mtk-scpsys.ko')]","prefix=modules[:28]")
    start=builder.index('    require(len(prefix)==32');end=builder.index("    put(entries,'etc/lynx/progress-modules.load'",start)
    builder=builder[:start]+"    require(len(prefix)==28 and prefix[-1]=='clk-mt6983-cam.ko','Unexpected one-module prefix')\n    put(entries,'etc/lynx/progress-count',b'28\\n',0o100644)\n"+builder[end:]
    builder=builder.replace("'113':'all32prefix insertions completed; binding not proven'","'0':'all28prefix insertions completed; binding not proven'")
    save(P/'prepare_module_progress_v2_image.py',builder)
    test=(T/'test_module_progress_control.py').read_text().replace('lynx-module-progress-runtime.sh','lynx-module-progress-v2-runtime.sh').replace('module-progress-control-','module-progress-v2-control-').replace("('success','success',0,113)","('success','success',0,0)")
    test=test.replace("modules=folder/'modules.load';", "(folder/'count').write_text('32\\n')\n        modules=folder/'modules.load';")
    test=test.replace(".replace('/proc/uptime',str(folder/'uptime'))", ".replace('/etc/lynx/progress-count',str(folder/'count')).replace('/proc/uptime',str(folder/'uptime'))")
    save(T/'test_module_progress_v2_control.py',test)
    native=(T/'test_native_power_clocks_v2.py').read_text().replace('emulated-native-power-clocks-v2-','emulated-native-initcall-debug-').replace('console=ttyAMA0 rdinit=/init loglevel=7 panic=0','console=ttyAMA0 rdinit=/init loglevel=7 panic=0 initcall_debug')
    marker="    passed=code==0 and all(checks.values())";assert native.count(marker)==1
    native=native.replace(marker,"    checks['stock_initcall_start_logged']=bool(re.search(rb'calling  .*clk_mt6983_cam.* @ ',raw))\n    checks['stock_initcall_return_logged']=bool(re.search(rb'initcall .*clk_mt6983_cam.*returned 0 after ',raw))\n"+marker,1)
    save(T/'test_native_initcall_debug.py',native)
    print('One-module sources and independent initcall test prepared; no phone contacted.')
if __name__=='__main__':main()
