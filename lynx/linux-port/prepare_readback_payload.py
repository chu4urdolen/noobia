"""Exercise the upstream loader patch entirely offline; never upload it."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import sys

base = Path(__file__).resolve().parent
sys.path.insert(0, str(base / 'sources/mtkclient-readback'))
from mtkclient.Library.DA.xmlflash.extension.v6 import XmlFlashExt

audit = json.loads((base / 'docs/download-agent-audit.json').read_text())
loader = (base / 'artifacts/service-reference/DA_BR.bin').read_bytes()
if hashlib.sha256(loader).hexdigest() != audit['loader_sha256']:
    raise ValueError('Loader changed')
region = audit['entries'][0]['regions'][2]
original = loader[region['file_offset']:region['file_offset'] + region['bytes']]
messages = []
context = object.__new__(XmlFlashExt)
context.config = SimpleNamespace(chipconfig=SimpleNamespace(has64bit=True))
context.mtk = SimpleNamespace(daloader=SimpleNamespace(daconfig=SimpleNamespace(
    da_loader=SimpleNamespace(region=[None, None, SimpleNamespace(m_start_addr=int(region['load_address'], 16))]))))
context.info = context.error = messages.append
report = {'loader_sha256': audit['loader_sha256'], 'original_da2_sha256': hashlib.sha256(original).hexdigest(),
          'phone_contacted': False, 'flash_eligible': False, 'patch_messages': messages}
try:
    patched = bytes(context.patch_da2(original))
    if len(patched) != len(original):
        raise ValueError('Upstream patch changed loader payload size')
    ranges = []
    start = None
    for i, (a, b) in enumerate(zip(original, patched)):
        if a != b and start is None:
            start = i
        elif a == b and start is not None:
            ranges.append({'offset': start, 'bytes': i - start})
            start = None
    if start is not None:
        ranges.append({'offset': start, 'bytes': len(original) - start})
    output = base / 'artifacts/service-reference/da2-upstream-patch-OFFLINE-ONLY.bin'
    output.write_bytes(patched)
    report.update(patched_da2_sha256=hashlib.sha256(patched).hexdigest(),
                  changed_ranges=ranges, changed_bytes=sum(r['bytes'] for r in ranges),
                  output=str(output), upstream_patch_completed_offline=True,
                  execution_authorized_by_this_report=False,
                  limits=['The generated patch changes erase/write policy checks; the upstream routine can also add custom-command code.',
                          'It is not a minimal authentication-only patch or a proven restoration route.',
                          'No patched code has run on Lynx.'])
except Exception as error:
    report.update(upstream_patch_completed_offline=False, error=str(error))
(base / 'docs/ram-payload-preparation.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
