"""Preserve the historical diagnostic, disable its flash path, retain undo."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
folder = ROOT / 'linux-port/artifacts/busybox-mtu3-timed-supervisor'
tool = ROOT / 'tools/lynx_boot_a_mtu3_supervisor_trial.py'
validator = ROOT / 'tools/validate_mtu3_supervisor.py'
original = tool.read_text()
assert not (folder / 'trial-tool-before-retirement.py').exists(), 'Already retired'
(folder / 'trial-tool-before-retirement.py').write_text(original)
(folder / 'validator-before-retirement.py').write_bytes(validator.read_bytes())
init = (folder / 'init-source').read_bytes()
start = init.index(b'# Runtime state lives only in tmpfs.')
end = init.index(b"\nlynx_mtu3_supervise || log 'SUPERVISOR_REFUSED_OR_FAILED'", start)
source = init[start:end]
assert hashlib.sha256(source).hexdigest() == '3ba341e4d62c3fe61f0200209bb06032872b5524fdce29de2f6317adffb74bc0'
(folder / 'supervisor-source-before-null-fix').write_bytes(source)
needle = '    args = parser.parse_args()\n'
assert original.count(needle) == 1
retired = original.replace(needle, needle + "    if not args.restore_stock:\n        raise ValueError('Retired diagnostic: missing /dev/null. Only verified stock restoration is supported.')\n")
begin = retired.index('    validation = subprocess.run(')
end = retired.index('    baseline_path = ', begin)
# Linux-image source changes must never prevent a verified stock-only undo.
# Image/stock hashes, OTA receipts, baseline, Fastboot binary and fresh identity
# guards remain in place below; no other partition can be written.
retired = retired[:begin] + retired[end:]
compile(retired, str(tool), 'exec')
tool.write_text(retired)
(folder / 'retirement.json').write_text(json.dumps(dict(reason='Missing /dev/null prevented ash background child startup.', original_trial_tool_sha256=hashlib.sha256(original.encode()).hexdigest(), restoration_tool_sha256=hashlib.sha256(retired.encode()).hexdigest(), linux_flash_disabled=True, stock_undo_preserved=True, phone_contacted=False), indent=2) + '\n')
print('Historical flash path retired; stock-only undo preserved:', tool)
