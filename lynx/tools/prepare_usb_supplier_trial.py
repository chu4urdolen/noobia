"""Prepare the fixed all-suppliers/no-MTU3 trial; do not contact phone."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent
target = ROOT / 'lynx_boot_a_usb_prefix_33_trial.py'
assert not target.exists(), 'Preserve existing tool'
source = (ROOT / 'lynx_boot_a_usb_prefix_26_trial.py').read_text()
for before, after in [
    ('busybox-usb-module-prefixes/26', 'busybox-usb-module-checkpoints/suppliers'),
    ('d55a995c513572af8dc5f72476962ca086e0b301a6ea143e81d78f032be1e344', '0208f76c1ef5d7e523dbf83226c208f0a0d8f2c08768cbbdfb79025275fd9ece'),
    ("'--prefix', '26'", "'--prefix', '33'"),
    ("'module_prefix_count': 26", "'module_prefix_count': 33"),
    ('boot-a-usb-prefix-26-trial-', 'boot-a-usb-prefix-33-trial-'),
    ('usb-prefix-26-observer-', 'usb-prefix-33-observer-'),
]:
    assert source.count(before) == 1, 'Reviewed source changed: ' + before
    source = source.replace(before, after)
compile(source, str(target), 'exec')
target.write_text(source)
print(target)
