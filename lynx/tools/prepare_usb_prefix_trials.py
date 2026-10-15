"""Freeze timed boot_a-only tools for independently validated module prefixes."""
from pathlib import Path
from validate_usb_module_prefix import HASHES

ROOT = Path(__file__).resolve().parent
source = (ROOT / 'lynx_boot_a_usb_checkpoint_trial.py').read_text()
for count, digest in HASHES.items():
    if count == '33':
        continue  # Its preserved suppliers image uses a separate source path/tool.
    target = ROOT / ('lynx_boot_a_usb_prefix_' + count + '_trial.py')
    assert not target.exists(), 'Preserve existing tool'
    text = source
    changes = [
        ('busybox-usb-module-checkpoints/with-mtu3', 'busybox-usb-module-prefixes/' + count),
        ('5bb984899b19c9e739faa23aa9039374a5ad20ab99c10948d5d2b964da3616d6', digest),
        ("str(ROOT / 'tools/validate_usb_module_checkpoint.py')", "str(ROOT / 'tools/validate_usb_module_prefix.py'), '--prefix', '" + count + "'"),
        ('boot-a-usb-checkpoint-trial-', 'boot-a-usb-prefix-' + count + '-trial-'),
        ('usb-checkpoint-observer-', 'usb-prefix-' + count + '-observer-'),
    ]
    for before, after in changes:
        assert text.count(before) == 1, 'Reviewed source changed: ' + before
        text = text.replace(before, after)
    text = text.replace("'mode': 'offline-readiness',", "'mode': 'offline-readiness', 'module_prefix_count': " + count + ", 'tool_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'observer_tool_sha256': hashlib.sha256((ROOT/'tools/lynx_trial_observer.py').read_bytes()).hexdigest(),")
    assert text.count("'module_prefix_count'") == 1
    compile(text, str(target), 'exec')
    target.write_text(text)
    print(target)
