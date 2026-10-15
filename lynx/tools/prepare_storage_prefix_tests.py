"""Pin local tests, independent validation, and scoped trial for storage prefix."""
from pathlib import Path
T=Path(__file__).resolve().parent
OLD='6070a324cbbfc8a1262b94ae111e3a6b3a4cb330e66af54d2363a3e2c5b7edad'
NEW='18a5250d0617c03a305381b6aa24e37a0f2681463e441f7771a586df4a2ec540'
def save(name,text):
    path=T/name;assert not path.exists();compile(text,str(path),'exec');path.write_text(text)
def main():
    native=(T/'test_native_power_controller_progress.py').read_text().replace('choices=[0,28,32,34]','choices=[40]').replace("34:'"+OLD+"'}", "34:'"+OLD+"',40:'"+NEW+"'}")
    native=native.replace('lynx-power-controller-progress-runtime.sh','lynx-storage-prefix-progress-runtime.sh').replace('/lib/modules/mtk-scpsys-mt6983.ko','/lib/modules/blocktag.ko').replace("'114' if args.count else '0'","'120'").replace('emulated-native-module-progress-debug-v2-','emulated-native-storage-prefix-progress-')
    save('test_native_storage_prefix_progress.py',native)
    guard=(T/'test_power_controller_progress_guard.py').read_text().replace('choices=[0,28,32,34]','choices=[40]')
    save('test_storage_prefix_progress_guard.py',guard)
    validator=(T/'validate_power_controller_progress_image.py').read_text().replace('choices=[0,28,32,34]','choices=[40]').replace("34:'"+OLD+"'}", "34:'"+OLD+"',40:'"+NEW+"'}")
    validator=validator.replace(".splitlines()[:args.count]", ".splitlines()[:34]+old['etc/lynx/bootstrap-storage-modules.load']['data'].decode().splitlines()[:6]")
    validator=validator.replace('lynx-power-controller-progress-runtime.sh','lynx-storage-prefix-progress-runtime.sh').replace('power-controller-progress-control-','storage-prefix-progress-control-').replace("glob('emulated-native-module-progress-debug-*/result.json')", "glob('emulated-native-storage-prefix-progress-*/result.json')").replace('module-progress-dependencies.json','storage-prefix-dependencies.json')
    save('validate_storage_prefix_progress_image.py',validator)
    audit=(T/'audit_progress_dependencies.py').read_text().replace('busybox-module-progress-debug-28-v1','busybox-module-progress-debug-40-v1').replace('module-progress-dependencies.json','storage-prefix-dependencies.json')
    save('audit_storage_prefix_dependencies.py',audit)
    trial=(T/'lynx_boot_a_power_controller_progress_trial.py').read_text().replace('busybox-module-progress-debug-34-v1','busybox-module-progress-debug-40-v1').replace(OLD,NEW).replace('validate_power_controller_progress_image.py','validate_storage_prefix_progress_image.py').replace("'--count', '34'", "'--count', '40'").replace('boot-a-progress-debug-34-trial-','boot-a-storage-prefix-trial-').replace("'module_prefix_count': 34", "'module_prefix_count': 40").replace('stock power-controller library and driver with per-module checkpoints','six storage prerequisites only; main UFS and payload read excluded')
    save('lynx_boot_a_storage_prefix_trial.py',trial)
    print('Storage prerequisite tests and scoped trial prepared.')
if __name__=='__main__':main()
