"""Prepare pinned offline control/guard/validation and boot_a-only trial tools."""
from pathlib import Path
T=Path(__file__).resolve().parent
OLD='6070a324cbbfc8a1262b94ae111e3a6b3a4cb330e66af54d2363a3e2c5b7edad'
NEW='476997a9b518d951f075194004cf288e0214741f571810f8932009b8c585d11e'
def save(name,text):
    path=T/name;assert not path.exists();compile(text,str(path),'exec');path.write_text(text)
def main():
    control=(T/'test_power_controller_progress_control.py').read_text().replace('lynx-power-controller-progress-runtime.sh','lynx-essential-storage-progress-runtime.sh').replace('power-controller-progress-control-','essential-storage-progress-control-')
    control=control.replace('range(28,35)','range(1,42)').replace('range(1,35)','range(1,42)').replace("write_text('34\\n')","write_text('41\\n')").replace("1,81)","1,85)").replace('index+80','index+84')
    control=control.replace("+log+source+'\\nlynx_module_progress\\n'", "+log+source+'\\nlynx_storage_payload_checkpoint() { return 0; }\\nlynx_module_progress\\n'")
    save('test_essential_storage_progress_control.py',control)
    native=(T/'test_native_power_controller_progress.py').read_text().replace('choices=[0,28,32,34]','choices=[41]').replace("34:'"+OLD+"'}", "34:'"+OLD+"',41:'"+NEW+"'}")
    native=native.replace('lynx-power-controller-progress-runtime.sh','lynx-essential-storage-progress-runtime.sh').replace('/lib/modules/mtk-scpsys-mt6983.ko','/lib/modules/ufs-mediatek-mod.ko').replace("'114' if args.count else '0'","'125'")
    native=native.replace("echo NATIVE_PROGRESS_SUCCESS_BEGIN", "lynx_storage_payload_checkpoint() { [ ! -f /run/fail-payload ]; }\necho NATIVE_PROGRESS_SUCCESS_BEGIN")
    native=native.replace("$BB poweroff -f", """$BB rm /run/fail-clock /run/lynx/module-progress
$BB touch /run/fail-payload
echo NATIVE_PROGRESS_PAYLOAD_BEGIN
lynx_module_progress
printf 'NATIVE_PROGRESS_PAYLOAD_EXIT=%s\\n' "$?"
echo NATIVE_PAYLOAD_HEX_BEGIN
$BB cat /run/lynx/stages-bootstrap.hex
echo NATIVE_PAYLOAD_HEX_END
$BB cat /run/lynx/boot.log
$BB poweroff -f""")
    native=native.replace('timeout=60','timeout=85').replace("['SUCCESS','FAILURE']", "['SUCCESS','FAILURE','PAYLOAD']").replace("==2,", "==3,").replace('exactly_two_fake_resets','exactly_three_fake_resets')
    native=native.replace("'prefix_success':", "'payload_failure':b'MODULE_PROGRESS_FIELD code=126 target_delay=20' in raw, 'prefix_success':")
    native=native.replace('emulated-native-module-progress-debug-v2-','emulated-native-essential-storage-progress-')
    save('test_native_essential_storage_progress.py',native)
    guard=(T/'test_power_controller_progress_guard.py').read_text().replace('choices=[0,28,32,34]','choices=[41]')
    save('test_essential_storage_progress_guard.py',guard)
    validator=(T/'validate_power_controller_progress_image.py').read_text().replace('choices=[0,28,32,34]','choices=[41]').replace("34:'"+OLD+"'}", "34:'"+OLD+"',41:'"+NEW+"'}")
    validator=validator.replace(".splitlines()[:args.count]", ".splitlines()[:34]+old['etc/lynx/bootstrap-storage-modules.load']['data'].decode().splitlines()")
    validator=validator.replace("['ufs-mediatek-mod.ko','mtu3.ko']", "['mtu3.ko','phy-mtk-xsphy.ko','tcpc_mt6375.ko','extcon-mtk-usb.ko','xhci-mtk-hcd.ko','rpmb-mtk.ko']")
    validator=validator.replace('lynx-power-controller-progress-runtime.sh','lynx-essential-storage-progress-runtime.sh').replace('power-controller-progress-control-','essential-storage-progress-control-').replace("glob('emulated-native-module-progress-debug-*/result.json')", "glob('emulated-native-essential-storage-progress-*/result.json')")
    validator=validator.replace("n['checks']['native_hex_FAILURE']", "n['checks']['native_hex_FAILURE'] and n['checks']['native_hex_PAYLOAD'] and n['checks']['payload_failure']")
    save('validate_essential_storage_progress_image.py',validator)
    trial=(T/'lynx_boot_a_power_controller_progress_trial.py').read_text().replace('busybox-module-progress-debug-34-v1','busybox-module-progress-debug-41-v1').replace(OLD,NEW).replace('validate_power_controller_progress_image.py','validate_essential_storage_progress_image.py').replace("'--count', '34'", "'--count', '41'").replace('boot-a-progress-debug-34-trial-','boot-a-essential-storage-trial-').replace("'module_prefix_count': 34", "'module_prefix_count': 41").replace('stock power-controller library and driver with per-module checkpoints','essential UFS modules and read-only verified own boot payload checkpoint')
    save('lynx_boot_a_essential_storage_trial.py',trial)
    print('Essential storage tests prepared; no handset contacted.')
if __name__=='__main__':main()
