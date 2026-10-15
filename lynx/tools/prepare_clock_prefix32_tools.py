"""Reuse tested checkpoint logic with the remaining four stock clock suppliers."""
from pathlib import Path
T=Path(__file__).resolve().parent
OLD='9b5e9ff94c5c441e945ebc3bf714b253d2f8bcfbfcc91182b8d9baf54aeab0e4'
NEW='2468d6b65d4f3cd06927db51b9e077708e363a9ecdd112c568203cc4a3eea6dd'
def save(name,text):
    path=T/name;assert not path.exists();compile(text,str(path),'exec');path.write_text(text)
def main():
    native=(T/'test_native_module_progress_debug_v2.py').read_text().replace('choices=[0,28]','choices=[0,28,32]')
    native=native.replace("28:'"+OLD+"'}", "28:'"+OLD+"',32:'"+NEW+"'}")
    save('test_native_module_progress_debug_32.py',native)
    guard=(T/'test_module_progress_debug_guard.py').read_text().replace('choices=[0,28]','choices=[0,28,32]')
    save('test_module_progress_debug_32_guard.py',guard)
    validator=(T/'validate_progress_debug_image.py').read_text().replace('choices=[0,28]','choices=[0,28,32]').replace("28:'"+OLD+"'}", "28:'"+OLD+"',32:'"+NEW+"'}")
    save('validate_progress_debug_32_image.py',validator)
    trial=(T/'lynx_boot_a_progress_debug_28_trial.py').read_text().replace('busybox-module-progress-debug-28-v1','busybox-module-progress-debug-32-v1').replace(OLD,NEW).replace('validate_progress_debug_image.py','validate_progress_debug_32_image.py').replace("'--count', '28'","'--count', '32'").replace('boot-a-progress-debug-28-trial-','boot-a-progress-debug-32-trial-').replace("'module_prefix_count': 28","'module_prefix_count': 32").replace('one additional camera clock module with per-module checkpoints','remaining stock clock modules with per-module checkpoints')
    save('lynx_boot_a_progress_debug_32_trial.py',trial)
    print('Remaining clock checkpoint tools prepared; no handset contacted.')
if __name__=='__main__':main()
