"""Derive pinned guard and trial harnesses without changing prior experiments."""
from pathlib import Path
R=Path(__file__).resolve().parent.parent;T=R/'tools'
def save(name,source):
    path=T/name
    assert not path.exists(),path
    compile(source,str(path),'exec');path.write_text(source)
def main():
    source=(T/'test_storage_prefix_progress_guard.py').read_text()
    source=source.replace("('busybox-module-progress-debug-'+str(args.count)+'-v1')", "'busybox-ufs-registration-only-v1'")
    source=source.replace("'emulated-module-progress-debug-guard-'+str(args.count)+'-'", "'emulated-ufs-registration-guard-'")
    source=source.replace("'cortex-a72'", "'cortex-a710'")
    save('test_ufs_registration_image_guard.py',source)
    source=(T/'lynx_boot_a_storage_prefix_trial.py').read_text()
    source=source.replace('from lynx_progress_timing import', 'from lynx_ufs_registration_timing import')
    source=source.replace('busybox-module-progress-debug-40-v1','busybox-ufs-registration-only-v1')
    source=source.replace('18a5250d0617c03a305381b6aa24e37a0f2681463e441f7771a586df4a2ec540','034177798aed0cb0210e51eaf563eefc055abe6fcdbde3d272f89003b1880a56')
    source=source.replace("str(ROOT / 'tools/validate_storage_prefix_progress_image.py'), '--count', '40'", "str(ROOT / 'tools/validate_ufs_registration_image.py')")
    source=source.replace('six storage prerequisites only; main UFS and payload read excluded','stock UFS registration with verified RAM-only match override; hardware probing and payload read excluded')
    source=source.replace('boot-a-storage-prefix-trial-', 'boot-a-ufs-registration-trial-')
    source=source.replace('420 seconds','240 seconds').replace('time.monotonic()+420','time.monotonic()+240')
    save('lynx_boot_a_ufs_registration_trial.py',source)
    print('Derived exact guard and boot_a-only trial harnesses; no phone contacted.')
if __name__=='__main__':main()
