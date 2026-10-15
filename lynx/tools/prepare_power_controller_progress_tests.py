"""Pin native, guard, validation and trial tools for the controller checkpoint."""
from pathlib import Path
T=Path(__file__).resolve().parent
OLD='2468d6b65d4f3cd06927db51b9e077708e363a9ecdd112c568203cc4a3eea6dd'
NEW='6070a324cbbfc8a1262b94ae111e3a6b3a4cb330e66af54d2363a3e2c5b7edad'
def save(name,text):
    path=T/name;assert not path.exists();compile(text,str(path),'exec');path.write_text(text)
def main():
    native=(T/'test_native_module_progress_debug_32.py').read_text().replace('choices=[0,28,32]','choices=[0,28,32,34]')
    native=native.replace("32:'"+OLD+"'}","32:'"+OLD+"',34:'"+NEW+"'}")
    native=native.replace('lynx-module-progress-debug-runtime.sh','lynx-power-controller-progress-runtime.sh').replace('/lib/modules/clk-mt6983-cam.ko','/lib/modules/mtk-scpsys-mt6983.ko').replace("'108' if args.count else '0'","'114' if args.count else '0'").replace("'first_clock_failure'","'controller_failure'")
    save('test_native_power_controller_progress.py',native)
    guard=(T/'test_module_progress_debug_32_guard.py').read_text().replace('choices=[0,28,32]','choices=[0,28,32,34]')
    save('test_power_controller_progress_guard.py',guard)
    validator=(T/'validate_progress_debug_32_image.py').read_text().replace('choices=[0,28,32]','choices=[0,28,32,34]').replace("32:'"+OLD+"'}","32:'"+OLD+"',34:'"+NEW+"'}")
    validator=validator.replace("['mtk-scpsys.ko','mtk-scpsys-mt6983.ko','ufs-mediatek-mod.ko','mtu3.ko']","['ufs-mediatek-mod.ko','mtu3.ko']")
    validator=validator.replace('lynx-module-progress-debug-runtime.sh','lynx-power-controller-progress-runtime.sh').replace('module-progress-debug-control-','power-controller-progress-control-')
    save('validate_power_controller_progress_image.py',validator)
    trial=(T/'lynx_boot_a_progress_debug_32_trial.py').read_text().replace('busybox-module-progress-debug-32-v1','busybox-module-progress-debug-34-v1').replace(OLD,NEW).replace('validate_progress_debug_32_image.py','validate_power_controller_progress_image.py').replace("'--count', '32'","'--count', '34'").replace('boot-a-progress-debug-32-trial-','boot-a-progress-debug-34-trial-').replace("'module_prefix_count': 32","'module_prefix_count': 34").replace('remaining stock clock modules with per-module checkpoints','stock power-controller library and driver with per-module checkpoints')
    save('lynx_boot_a_power_controller_progress_trial.py',trial)
    print('Controller checkpoint tests/trial prepared; no phone contacted.')
if __name__=='__main__':main()
