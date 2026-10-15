"""Check closely related manufacturer EU endpoints for this exact object."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import time
import urllib.request

BASE = Path(__file__).resolve().parent
reference = json.loads((BASE.parent / 'downloads/august-eu-parallel-download.json').read_text())
tail = '/remove-59822b61319727ba9ca6f2fd62dc0ef2/component-ota/23/08/14/4f1a650f088f4be39da1e6103015aa24.zip'
hosts = ('gauss-otacostmanual-eu.allawnofs.com', 'gauss-opexcostauto-eu.allawnofs.com',
         'gauss-otacostauto-eu.allawnofs.com', 'gauss-componentotacostmanual-eu.allawnofs.com')


def probe(host):
    url = 'https://' + host + tail
    result = {'url': url}
    started = time.monotonic()
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={
                'Range': 'bytes=0-1048575', 'If-Match': reference['etag']}), timeout=10) as response:
            if response.status != 206 or response.headers.get('Content-Range') != f'bytes 0-1048575/{reference["archive_bytes"]}':
                raise ValueError('Range or object size mismatch')
            if response.headers.get('ETag') != reference['etag']:
                raise ValueError('Object ETag mismatch')
            data = response.read(1048577)
            if len(data) != 1048576:
                raise ValueError('Unexpected response length')
            result.update(usable=True, sha256=hashlib.sha256(data).hexdigest())
    except Exception as error:
        result.update(usable=False, error=str(error))
    result['elapsed_seconds'] = round(time.monotonic() - started, 2)
    print(json.dumps(result), flush=True)
    return result


with ThreadPoolExecutor(max_workers=4) as executor:
    results = list(executor.map(probe, hosts))
(BASE / 'docs/august-eu-mirror-benchmark.json').write_text(json.dumps(results, indent=2) + '\n')
