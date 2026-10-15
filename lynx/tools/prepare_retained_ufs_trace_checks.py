"""Preserve prior checks; derive ARM64/guard/timing tools for the new query."""
from pathlib import Path
R=Path(__file__).resolve().parent.parent;T=R/'tools'
SHA='299c1ab3207e48d546077506690a1cfb91bdf05d0fe2c63d3a56dc4feff5ef75'
def save(name,source):
    out=T/name;assert not out.exists(),out;compile(source,str(out),'exec');out.write_text(source)
def main():
    source=(T/'test_native_retained_stage.py').read_text().replace('busybox-retained-stage-query-v1','busybox-retained-ufs-trace-query-v1').replace('1dc206e7ba79067711957f9d8b40ea19d53594b38a4d7e51026275035262bc52',SHA).replace('lynx-retained-stage-runtime.sh','lynx-retained-ufs-trace-runtime.sh').replace('emulated-native-retained-stage-','emulated-native-retained-ufs-trace-')
    start=source.index("put(entries,'fixture/pstore/sample',");end=source.index(',0o100600)',start)+len(',0o100600)')
    fixture="put(entries,'fixture/pstore/sample',(payload+' '+hashlib.sha256(payload.encode()).hexdigest()+chr(10)+'lx'+reference_token+'_4: (fixture-function+0x0/0x20)'+chr(10)).encode(),0o100600)"
    source=source[:start]+fixture+source[end:]
    marker="    put(entries,'fixture',"
    source=source.replace(marker,"    reference_token=entries['etc/lynx/reference-ufs-token']['data'].decode().strip()\n    payload=f'LXDG1 {reference_token} 00000001 0000000a 0203 0011'\n"+marker)
    source=source.replace("code=1 target_delay=20' in raw", "code=4 target_delay=20' in raw").replace("+'128'+", "+'16'+")
    save('test_native_retained_ufs_trace.py',source)
    source=(T/'test_storage_prefix_progress_guard.py').read_text().replace('choices=[40]','choices=[34]').replace("('busybox-module-progress-debug-'+str(args.count)+'-v1')","'busybox-retained-ufs-trace-query-v1'").replace("'emulated-module-progress-debug-guard-'+str(args.count)+'-'","'emulated-retained-ufs-trace-guard-'").replace("'cortex-a72'","'cortex-a710'")
    save('test_retained_ufs_trace_guard.py',source)
    source=(T/'lynx_ufs_registration_timing.py').read_text().replace('range(6)','range(19)').replace('UFS registration','Retained UFS trace')
    save('lynx_retained_ufs_trace_timing.py',source)
    source=(T/'test_ufs_registration_timing.py').read_text().replace('lynx_ufs_registration_timing','lynx_retained_ufs_trace_timing').replace('busybox-ufs-registration-only-v1','busybox-retained-ufs-trace-query-v1').replace('range(6)','range(19)').replace('range(5)','range(18)').replace('baseline+160','baseline+240').replace('ufs-registration-timing-test','retained-ufs-trace-timing-test')
    save('test_retained_ufs_trace_timing.py',source)
    source=(T/'lynx_boot_a_ufs_registration_trial.py').read_text().replace('lynx_ufs_registration_timing','lynx_retained_ufs_trace_timing').replace('busybox-ufs-registration-only-v1','busybox-retained-ufs-trace-query-v1').replace('034177798aed0cb0210e51eaf563eefc055abe6fcdbde3d272f89003b1880a56',SHA).replace('validate_ufs_registration_image','validate_retained_ufs_trace_image').replace('boot-a-ufs-registration-trial-','boot-a-retained-ufs-trace-trial-').replace('240 seconds','270 seconds').replace('time.monotonic()+240','time.monotonic()+270').replace("'module_prefix_count': 40","'module_prefix_count': 34").replace('stock UFS registration with verified RAM-only match override; hardware probing and payload read excluded','bounded read-only retained logs; main UFS insertion, payload and radio excluded')
    source=source.replace("str(ROOT / 'tools/validate_retained_ufs_trace_image.py')]", "str(ROOT / 'tools/validate_retained_ufs_trace_image.py'), '--count', '34']")
    save('lynx_boot_a_retained_ufs_trace_trial.py',source)
    print('Native/guard/timing/trial checks prepared; no phone contacted.')
if __name__=='__main__':main()
