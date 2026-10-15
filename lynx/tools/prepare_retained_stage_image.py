"""Encode common UFS marker outcomes first, retaining every valid source status."""
from pathlib import Path
import sys
R=Path(__file__).resolve().parent.parent;P=R/'linux-port';sys.path.insert(0,str(P))
source=(R/'tools/prepare_retained_log_image.py').read_text().replace('lynx-retained-log-runtime.sh','lynx-retained-stage-runtime.sh').replace('busybox-retained-log-query-v1','busybox-retained-stage-query-v1')
# Update the embedded builder construction, preserving its original source/reference.
source=source.replace('    flags={1:', '    flags={1:',1)
start=source.index('codes="""');end=source.index('source=source[:start]+codes+source[end:]',start)
codes='''codes="""    reference_manifest=json.loads((P/'artifacts/busybox-ufs-probe-emergency-v1/build-validation.json').read_text())
    reference_codes=reference_manifest['result_codes']
    statuses=[41,83,125,0]+[n for n in range(len(reference_codes)) if n not in [41,83,125,0] and not reference_codes[str(n)].startswith('reserved')]
    progress_map={str(i):n for i,n in enumerate(statuses,1)}
    put(entries,'etc/lynx/reference-progress-map',(''.join(str(status)+' '+code+chr(10) for code,status in progress_map.items())).encode(),0o100644)
    codes={str(n):'reserved; do not interpret' for n in range(131)}
    codes['0']='no checksum-valid reference progress marker found in selected bounded record'
    for code,status in progress_map.items():codes[code]='last retained reference marker: '+reference_codes[str(status)]
    codes.update({'126':'known base prefix pending','127':'retained stage query pending','128':'base module insertion failed','129':'reference/progress map invalid','130':'worker progress unavailable'})
"""
'''
source=source[:start]+codes+source[end:]
source=source.replace("source=source[:start]+codes+source[end:]", "source=source[:start]+codes+source[end:]\nsource=source.replace('    rd=pack(entries);','    rd=pack(entries);')")
# The map must be inserted before packing, not merely into the later report.
source=source.replace("source=source[:start]+codes+source[end:]\nsource=source.replace('    rd=pack(entries);','    rd=pack(entries);')", "source=source[:start]+codes+source[end:]\nmap_start=source.index('    reference_manifest=json.loads');map_end=source.index('    codes={',map_start)\nmap_setup=source[map_start:map_end]\nsource=source[:map_start]+source[map_end:]\nsource=source.replace('    rd=pack(entries);',map_setup+'    rd=pack(entries);')")
source=source.replace('range(70)','range(131)').replace('observation_seconds=540','observation_seconds=900').replace('retained_log_query=True,reference_ufs_token=reference,','retained_stage_query=True,reference_ufs_token=reference,reference_progress_map=progress_map,')
exec(compile(source,str(R/'tools/prepare_retained_log_image.py'),'exec'),{'__name__':'__main__','__file__':str(R/'tools/prepare_retained_log_image.py')})
