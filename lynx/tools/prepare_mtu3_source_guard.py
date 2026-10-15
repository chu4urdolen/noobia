"""Write an applicable source guard matching the audited machine-code exit."""
import difflib
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROJECT = ROOT / 'linux-port'
folder = PROJECT / 'artifacts/mtu3-null-child-guard'
source = PROJECT / 'sources/early-boot-reference/drivers/usb/mtu3/mtu3_host.c'
before = source.read_text()
needle = '\t\t\tpdev = of_find_device_by_node(child);\n\t\t\tif (pdev) {\n'
assert before.count(needle) == 1, 'Reviewed source changed'
after = before.replace(needle, needle + '\t\t\t\tif (!pdev->dev.driver)\n\t\t\t\t\tbreak;\n')
patch = ''.join(difflib.unified_diff(before.splitlines(keepends=True), after.splitlines(keepends=True), fromfile='a/drivers/usb/mtu3/mtu3_host.c', tofile='b/drivers/usb/mtu3/mtu3_host.c'))
target = folder / 'source-null-child-guard.patch'
assert not target.exists(), 'Preserve source patch'
target.write_text(patch)
(folder / 'mtu3_host.guarded.c').write_text(after)
(folder / 'source-guard-manifest.json').write_text(json.dumps(dict(source=str(source), source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(), guarded_source_sha256=hashlib.sha256(after.encode()).hexdigest(), patch_sha256=hashlib.sha256(patch.encode()).hexdigest(), behavior='Break on an unbound matching child, leaving cached platform-driver pointer untouched; do not derive container from NULL.', phone_contacted=False, compiled_from_this_source=False, limits='Source equivalent for future compatible rebuild; current guarded stock module uses the independently validated fixed instruction change.'), indent=2) + '\n')
print(target)
