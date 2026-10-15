"""Freeze the bounded log reader with the exact failed-UFS reference token."""
from pathlib import Path
import sys
R=Path(__file__).resolve().parent.parent;P=R/'linux-port';sys.path.insert(0,str(P))
source=(P/'prepare_power_controller_progress_image.py').read_text().replace('lynx-power-controller-progress-runtime.sh','lynx-retained-log-runtime.sh').replace("'busybox-module-progress-debug-'+str(args.count)+'-v1'", "'busybox-retained-log-query-v1'")
marker="    token=secrets.token_hex(16);"
source=source.replace(marker,"    reference=json.loads((P/'artifacts/busybox-ufs-probe-emergency-v1/build-validation.json').read_text())['session_token'];put(entries,'etc/lynx/reference-ufs-token',(reference+'\\n').encode(),0o100644)\n"+marker)
start=source.index('    for i,name in enumerate(prefix,1):');end=source.index('    report=json.loads',start)
codes="""    flags={1:'bounded record data read',2:'failed-UFS token text present',4:'matching stage checksum valid',8:'panic/oops marker present',16:'CFI failure marker present',32:'UFS/power/clock/SMC call-trace marker present'}
    for code in range(64):
        if code and not code&1:continue
        if code&4 and not code&2:continue
        codes[str(code)]='selected retained record: '+(', '.join(text for bit,text in flags.items() if code&bit) or 'no nonempty record read')
    codes.update({'64':'known base prefix pending','65':'bounded log query pending','66':'base module insertion failed','68':'malformed progress/reference record','69':'worker progress unavailable'})
"""
source=source[:start]+codes+source[end:]
source=source.replace('range(128)','range(70)').replace('120+2*n','120+5*n').replace('timing_match_tolerance_seconds=0.8','timing_match_tolerance_seconds=2.0').replace('observation_seconds=420','observation_seconds=540')
source=source.replace('module_progress_count=args.count,','module_progress_count=args.count,retained_log_query=True,reference_ufs_token=reference,')
exec(compile(source,str(P/'prepare_power_controller_progress_image.py'),'exec'),{'__name__':'__main__','__file__':str(P/'prepare_power_controller_progress_image.py')})
