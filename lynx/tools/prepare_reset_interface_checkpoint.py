"""Check the handset SysRq interface with harmless help, normal reset only."""
from pathlib import Path
R=Path(__file__).resolve().parent.parent;P=R/'linux-port'
def save(path,text):
    assert not path.exists(),str(path)
    if path.suffix=='.py':compile(text,str(path),'exec')
    path.write_text(text)
source=(P/'lynx-module-progress-debug-runtime.sh').read_text().replace('in 0|28|29|30|31|32)','in 0)')
source=source.replace('# Clock registration checkpoint only: no scpsys, UFS, radio or network startup.','# Harmless reset-interface help request only; no extra modules or emergency reset.')
old="        lynx_progress_write 0 || exit 1\n        log 'PROGRESS_SELECTED_PREFIX_INSERTIONS_COMPLETED; BINDING_NOT_PROVEN'"
new="""        lynx_progress_write 3 || exit 1
        if [ ! -e /proc/sysrq-trigger ]; then
            lynx_progress_write 2 || exit 1
        elif (printf 'h' > /proc/sysrq-trigger) 2>/dev/null; then
            lynx_progress_write 0 || exit 1
        else
            lynx_progress_write 1 || exit 1
        fi
        log 'RESET_INTERFACE_HELP_CHECK_COMPLETED'
"""
assert source.count(old)==1
save(P/'lynx-reset-interface-runtime.sh',source.replace(old,new))
builder=(P/'prepare_module_progress_debug_image.py').read_text().replace('choices=[0,28,29,30,31,32]','choices=[0]').replace("'busybox-module-progress-debug-'+str(args.count)+'-v1'", "'busybox-reset-interface-v1'").replace('lynx-module-progress-debug-runtime.sh','lynx-reset-interface-runtime.sh')
builder=builder.replace("'0':'all selected prefix insertions completed; binding not proven'", "'0':'SysRq help write accepted; emergency reset not executed','1':'SysRq help write rejected','2':'SysRq interface absent','3':'SysRq help request pending at sample'")
builder=builder.replace('calibration_only=args.count==0','calibration_only=False,reset_interface_check=True')
save(P/'prepare_reset_interface_image.py',builder)
print('Reset interface checkpoint prepared; no handset contacted.')
