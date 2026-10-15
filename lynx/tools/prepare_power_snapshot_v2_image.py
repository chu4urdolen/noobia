"""Build read-only power metadata snapshot from the frozen controller builder."""
from pathlib import Path
import sys
R=Path(__file__).resolve().parent.parent;P=R/'linux-port'
source=(P/'prepare_power_controller_progress_image.py').read_text().replace('lynx-power-controller-progress-runtime.sh','lynx-power-snapshot-v2-runtime.sh').replace("'busybox-module-progress-debug-'+str(args.count)+'-v1'", "'busybox-power-metadata-snapshot-v2'")
start=source.index('    for i,name in enumerate(prefix,1):');end=source.index('    report=json.loads',start)
codes="""    flags={1:'power-controller bound',2:'ufs0 domain object present',4:'debugfs mounted',8:'SysRq permission check writable'}
    for code in range(16):
        if code&2 and not code&4:continue
        codes[str(code)]='power metadata snapshot: '+(', '.join(text for bit,text in flags.items() if code&bit) or 'all queried flags absent')
    codes.update({'16':'known base module insertion failed','17':'known base module prefix still pending','18':'metadata query pending','125':'malformed progress record','127':'worker progress unavailable'})
"""
source=source[:start]+codes+source[end:]
source=source.replace('module_progress_count=args.count,','module_progress_count=args.count,power_metadata_snapshot=True,')
sys.path.insert(0,str(P))
source=source.replace("8:'SysRq permission check writable'", "8:'SysRq permission check writable',16:'persistent log file interface present'").replace('range(16):','range(32):')
source=source.replace("codes.update({'16':'known base module insertion failed','17':'known base module prefix still pending','18':'metadata query pending','125':'malformed progress record','127':'worker progress unavailable'})", "codes.update({str(32+i):'base insertion failed: '+name for i,name in enumerate(prefix,1)}); codes.update({'32':'known base module prefix still pending','67':'metadata query pending','68':'malformed progress record','69':'worker progress unavailable'})")
source=source.replace('range(128)','range(70)').replace('120+2*n','120+5*n').replace('timing_match_tolerance_seconds=0.8','timing_match_tolerance_seconds=2.0').replace('observation_seconds=420','observation_seconds=540')
exec(compile(source,str(P/'prepare_power_controller_progress_image.py'),'exec'),{'__name__':'__main__','__file__':str(P/'prepare_power_controller_progress_image.py')})
