"""Build read-only power metadata snapshot from the frozen controller builder."""
from pathlib import Path
import sys
R=Path(__file__).resolve().parent.parent;P=R/'linux-port'
source=(P/'prepare_power_controller_progress_image.py').read_text().replace('lynx-power-controller-progress-runtime.sh','lynx-power-snapshot-runtime.sh').replace("'busybox-module-progress-debug-'+str(args.count)+'-v1'", "'busybox-power-metadata-snapshot-v1'")
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
exec(compile(source,str(P/'prepare_power_controller_progress_image.py'),'exec'),{'__name__':'__main__','__file__':str(P/'prepare_power_controller_progress_image.py')})
