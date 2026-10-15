"""Freeze the timed boot_a-only guarded MTU3 checkpoint tool offline."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent
target = ROOT / 'lynx_boot_a_mtu3_guard_trial.py'
assert not target.exists(), 'Preserve existing trial'
source = (ROOT / 'lynx_boot_a_usb_prefix_33_trial.py').read_text()
for before, after in [
    ('busybox-usb-module-checkpoints/suppliers', 'busybox-mtu3-null-guard-checkpoint'),
    ('0208f76c1ef5d7e523dbf83226c208f0a0d8f2c08768cbbdfb79025275fd9ece', 'c815d527d6a4ff54f4ef2e04f968a7e4a6cf0a51e6e2eb1bba33df3e411c7c6c'),
    ("str(ROOT / 'tools/validate_usb_module_prefix.py'), '--prefix', '33'", "str(ROOT / 'tools/validate_mtu3_guard_checkpoint.py')"),
    ("'module_prefix_count': 33", "'module_prefix_count': 34, 'mtu3_null_child_guard': True"),
    ('boot-a-usb-prefix-33-trial-', 'boot-a-mtu3-guard-trial-'),
    ('usb-prefix-33-observer-', 'usb-mtu3-guard-observer-'),
]:
    assert source.count(before) == 1, 'Reviewed source changed: ' + before
    source = source.replace(before, after)
compile(source, str(target), 'exec')
target.write_text(source)
print(target)
