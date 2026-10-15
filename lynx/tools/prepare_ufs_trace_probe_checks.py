"""Prepare separate pinned checks/trial tools; preserve all earlier experiments."""
from pathlib import Path
R=Path(__file__).resolve().parent.parent;T=R/'tools'
SHA='30a2757ef742a859a24d577b35bf33111c3ed3cc5d43baa4199cf0d889f363ff'
def save(name,source):
    path=T/name;assert not path.exists(),path;compile(source,str(path),'exec');path.write_text(source)
def main():
    source=(T/'test_ufs_registration_image_guard.py').read_text().replace('busybox-ufs-registration-only-v1','busybox-ufs-trace-probe-v1').replace('emulated-ufs-registration-guard-','emulated-ufs-trace-probe-guard-')
    save('test_ufs_trace_probe_image_guard.py',source)
    source=(T/'lynx_ufs_registration_timing.py').read_text().replace('range(6)','range(10)').replace('UFS registration','UFS trace probe')
    save('lynx_ufs_trace_probe_timing.py',source)
    source=(T/'test_ufs_registration_timing.py').read_text().replace('lynx_ufs_registration_timing','lynx_ufs_trace_probe_timing').replace('busybox-ufs-registration-only-v1','busybox-ufs-trace-probe-v1').replace('range(6)','range(10)').replace('range(5)','range(9)').replace('baseline+160','baseline+180').replace('ufs-registration-timing-test','ufs-trace-probe-timing-test')
    save('test_ufs_trace_probe_timing.py',source)
    source=(T/'lynx_boot_a_ufs_registration_trial.py').read_text().replace('lynx_ufs_registration_timing','lynx_ufs_trace_probe_timing').replace('busybox-ufs-registration-only-v1','busybox-ufs-trace-probe-v1').replace('034177798aed0cb0210e51eaf563eefc055abe6fcdbde3d272f89003b1880a56',SHA).replace('validate_ufs_registration_image','validate_ufs_trace_probe_image').replace('boot-a-ufs-registration-trial-','boot-a-ufs-trace-probe-trial-').replace('stock UFS registration with verified RAM-only match override; hardware probing and payload read excluded','stock UFS loaded under match guard, nine trace events armed, exact UFS device reprobe; storage writes and payload read excluded')
    save('lynx_boot_a_ufs_trace_probe_trial.py',source)
    print('Separate traced-probe checks and boot_a-only trial tool prepared; no phone contacted.')
if __name__=='__main__':main()
