"""Prepare the next two sequential insertions: scpsys library and MT6983 driver."""
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent;P=ROOT/'linux-port';T=ROOT/'tools'
def save(path,text):
    assert not path.exists();compile(text,str(path),'exec') if path.suffix=='.py' else None;path.write_text(text)
def main():
    runtime=(P/'lynx-module-progress-debug-runtime.sh').read_text().replace('in 0|28|29|30|31|32)','in 0|28|29|30|31|32|34)')
    save(P/'lynx-power-controller-progress-runtime.sh',runtime)
    builder=(P/'prepare_module_progress_debug_image.py').read_text().replace('choices=[0,28,29,30,31,32]','choices=[34]').replace('lynx-module-progress-debug-runtime.sh','lynx-power-controller-progress-runtime.sh')
    builder=builder.replace("require(args.count==0 or prefix[-1].startswith('clk-mt6983-'),'Unexpected prefix')", "require(prefix[-2:]==['mtk-scpsys.ko','mtk-scpsys-mt6983.ko'],'Unexpected controller prefix')")
    save(P/'prepare_power_controller_progress_image.py',builder)
    control=(T/'test_module_progress_debug_control.py').read_text().replace('lynx-module-progress-debug-runtime.sh','lynx-power-controller-progress-runtime.sh').replace('module-progress-debug-control-','power-controller-progress-control-')
    control=control.replace("write_text('32\\n')","write_text('34\\n')").replace('range(1,33)','range(1,35)').replace('range(28,33)','range(28,35)')
    save(T/'test_power_controller_progress_control.py',control)
    print('Power-controller checkpoint sources prepared; no handset access.')
if __name__=='__main__':main()
