"""Widen snapshot timing and include exact module failures/log-interface presence."""
from pathlib import Path
import sys
R=Path(__file__).resolve().parent.parent;P=R/'linux-port'
def save(path,text):
    assert not path.exists();path.write_text(text)
runtime=(P/'lynx-power-snapshot-runtime.sh').read_text()
runtime=runtime.replace('lynx_progress_write 17','lynx_progress_write 32').replace('lynx_progress_write 16','lynx_progress_write "$((32+progress_index))"').replace('lynx_progress_write 18','lynx_progress_write 67')
runtime=runtime.replace('progress_code=127','progress_code=69').replace('progress_code=125','progress_code=68').replace('"$progress_code" -le 127','"$progress_code" -le 69').replace('120+2*progress_code','120+5*progress_code')
runtime=runtime.replace('    log "POWER_METADATA_SNAPSHOT', '''    snapshot_log_interface=0
    for snapshot_record in /sys/fs/pstore/* /proc/last_kmsg; do
        [ ! -f "$snapshot_record" ] || snapshot_log_interface=1
    done
    [ "$snapshot_log_interface" = 0 ] || snapshot_mask=$((snapshot_mask|16))
    log "POWER_METADATA_SNAPSHOT''')
save(P/'lynx-power-snapshot-v2-runtime.sh',runtime)
builder=(R/'tools/prepare_power_snapshot_image.py').read_text().replace('lynx-power-snapshot-runtime.sh','lynx-power-snapshot-v2-runtime.sh').replace('busybox-power-metadata-snapshot-v1','busybox-power-metadata-snapshot-v2')
# Expand the generator's replacements before its final exec.
old="exec(compile(source,str(P/'prepare_power_controller_progress_image.py'),'exec'),"
extra="""source=source.replace("8:'SysRq permission check writable'", "8:'SysRq permission check writable',16:'persistent log file interface present'").replace('range(16):','range(32):')
source=source.replace("codes.update({'16':'known base module insertion failed','17':'known base module prefix still pending','18':'metadata query pending','125':'malformed progress record','127':'worker progress unavailable'})", "codes.update({str(32+i):'base insertion failed: '+name for i,name in enumerate(prefix,1)}); codes.update({'32':'known base module prefix still pending','67':'metadata query pending','68':'malformed progress record','69':'worker progress unavailable'})")
source=source.replace('range(128)','range(70)').replace('120+2*n','120+5*n').replace('timing_match_tolerance_seconds=0.8','timing_match_tolerance_seconds=2.0').replace('observation_seconds=420','observation_seconds=540')
"""
assert old in builder
builder=builder.replace(old,extra+old)
save(R/'tools/prepare_power_snapshot_v2_image.py',builder)
print('Snapshot v2 sources prepared; no phone contacted.')
