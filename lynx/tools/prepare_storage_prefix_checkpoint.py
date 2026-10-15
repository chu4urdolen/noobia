"""Prepare six UFS prerequisites only; exclude UFS controller and payload read."""
from pathlib import Path
R=Path(__file__).resolve().parent.parent;P=R/'linux-port';T=R/'tools'
def save(path,text):
    assert not path.exists(),str(path)
    if path.suffix=='.py':compile(text,str(path),'exec')
    path.write_text(text)
def main():
    runtime=(P/'lynx-power-controller-progress-runtime.sh').read_text().replace('in 0|28|29|30|31|32|34)','in 40)')
    runtime=runtime.replace('# Clock registration checkpoint only: no scpsys, UFS, radio or network startup.','# Six essential UFS prerequisites; no main UFS driver, payload read or radio startup.')
    save(P/'lynx-storage-prefix-progress-runtime.sh',runtime)
    builder=(P/'prepare_power_controller_progress_image.py').read_text().replace('choices=[34]','choices=[40]').replace('lynx-power-controller-progress-runtime.sh','lynx-storage-prefix-progress-runtime.sh')
    builder=builder.replace('prefix=modules[:args.count]',"prefix=modules[:34]+entries['etc/lynx/bootstrap-storage-modules.load']['data'].decode().splitlines()[:6]")
    builder=builder.replace("require(prefix[-2:]==['mtk-scpsys.ko','mtk-scpsys-mt6983.ko'],'Unexpected controller prefix')", "require(len(prefix)==40 and prefix[-1]=='blocktag.ko' and 'ufs-mediatek-mod.ko' not in prefix,'Unexpected storage prefix')")
    save(P/'prepare_storage_prefix_progress_image.py',builder)
    control=(T/'test_power_controller_progress_control.py').read_text().replace('lynx-power-controller-progress-runtime.sh','lynx-storage-prefix-progress-runtime.sh').replace('power-controller-progress-control-','storage-prefix-progress-control-')
    control=control.replace("write_text('34\\n')","write_text('40\\n')").replace('range(1,35)','range(1,41)').replace('range(28,35)','range(35,41)')
    save(T/'test_storage_prefix_progress_control.py',control)
    print('Storage prerequisites checkpoint prepared; no handset access.')
if __name__=='__main__':main()
