"""Preserve AOSP's payload-signature format references beneath this workspace."""
import base64
import hashlib
import json
from pathlib import Path
import urllib.request

directory = Path(__file__).resolve().parent / 'sources/aosp-update-engine-reference'
directory.mkdir(exist_ok=True)
report = []
for path in ('payload_generator/payload_signer.cc', 'payload_consumer/payload_verifier.cc', 'update_metadata.proto'):
    url = 'https://android.googlesource.com/platform/system/update_engine/+/refs/heads/android13-release/' + path + '?format=TEXT'
    entry = {'url': url, 'path': path}
    try:
        with urllib.request.urlopen(url, timeout=20) as response:
            encoded = response.read(2 * 1024 * 1024)
        data = base64.b64decode(encoded, validate=True)
        target = directory / Path(path).name
        target.write_bytes(data)
        entry.update(file=str(target), sha256=hashlib.sha256(data).hexdigest(), bytes=len(data))
    except Exception as error:
        entry['error'] = str(error)
    report.append(entry)
(directory / 'source-manifest.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
