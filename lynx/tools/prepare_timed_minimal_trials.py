"""Prepare fixed minimal-image A/B tools from the guarded timed trial; offline."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent
source = (ROOT / 'lynx_boot_a_usb_checkpoint_trial.py').read_text()
cases = [
    ('reboot', 'busybox-August-boot-proof-bound-guards', 'a9a72334185a5ddec9b6e3ece6e9e01600582f62c4db7bebc8ce87c4d5c3fe43', 'validate_boot_proof.py'),
    ('hold', 'busybox-minimal-hold-control', '25040803f00546bda46ba58407f19e7dcf1978375466a210df360cbcdd2f9166', 'validate_boot_hold_control.py'),
]
for name, folder, digest, validator in cases:
    target = ROOT / ('lynx_boot_a_timed_minimal_' + name + '_trial.py')
    assert not target.exists(), 'Preserve existing trial tool'
    text = source
    for before, after in [
        ('busybox-usb-module-checkpoints/with-mtu3', folder),
        ('5bb984899b19c9e739faa23aa9039374a5ad20ab99c10948d5d2b964da3616d6', digest),
        ('validate_usb_module_checkpoint.py', validator),
        ('boot-a-usb-checkpoint-trial-', 'boot-a-timed-minimal-' + name + '-trial-'),
        ('usb-checkpoint-observer-', 'usb-minimal-' + name + '-observer-'),
    ]:
        assert text.count(before) == 1, 'Reviewed source changed: ' + before
        text = text.replace(before, after)
    text = text.replace("'mode': 'offline-readiness',", "'mode': 'offline-readiness', 'comparison_arm': '" + name + "', 'tool_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'observer_tool_sha256': hashlib.sha256((ROOT/'tools/lynx_trial_observer.py').read_bytes()).hexdigest(),")
    assert text.count("'comparison_arm'") == 1
    compile(text, str(target), 'exec')
    target.write_text(text)
    print(target)
