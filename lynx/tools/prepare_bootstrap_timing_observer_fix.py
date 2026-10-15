"""Preserve the first runner; correct future passive observation to360 seconds."""
from pathlib import Path
R=Path(__file__).resolve().parent.parent
source=(R/'tools/lynx_boot_a_bootstrap_timing_trial.py').read_text()
assert source.count('up to 270 seconds')==1 and source.count('time.monotonic()+270')==1
source=source.replace('up to 270 seconds','up to 360 seconds').replace('time.monotonic()+270','time.monotonic()+360').replace('boot-a-bootstrap-timing-trial-','boot-a-bootstrap-timing-v2-trial-')
out=R/'tools/lynx_boot_a_bootstrap_timing_v2_trial.py'
assert not out.exists();compile(source,str(out),'exec');out.write_text(source)
print(out)
