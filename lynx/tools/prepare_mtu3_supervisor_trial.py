"""Freeze fixed timed boot_a-only supervisor trial; no phone commands."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent
target = ROOT / 'lynx_boot_a_mtu3_supervisor_trial.py'
assert not target.exists(), 'Preserve existing trial'
source = (ROOT / 'lynx_boot_a_usb_prefix_33_trial.py').read_text()
for before, after in [
    ('busybox-usb-module-checkpoints/suppliers', 'busybox-mtu3-timed-supervisor'),
    ('0208f76c1ef5d7e523dbf83226c208f0a0d8f2c08768cbbdfb79025275fd9ece', 'adb55ffe21b8079c4e64a8eb48917c6566dcfd58763fa813bb10a635ad2b6b9a'),
    ("str(ROOT / 'tools/validate_usb_module_prefix.py'), '--prefix', '33'", "str(ROOT / 'tools/validate_mtu3_supervisor.py')"),
    ("'module_prefix_count': 33", "'module_prefix_count': 33, 'mtu3_child_supervisor': True, 'child_relative_reset_seconds': [20,40,60]"),
    ('boot-a-usb-prefix-33-trial-', 'boot-a-mtu3-supervisor-trial-'),
    ('usb-prefix-33-observer-', 'usb-mtu3-supervisor-observer-'),
]:
    assert source.count(before) == 1, 'Reviewed source changed: ' + before
    source = source.replace(before, after)
compile(source, str(target), 'exec')
target.write_text(source)
print(target)
