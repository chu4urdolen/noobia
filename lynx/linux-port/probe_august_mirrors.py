"""Check remaining manufacturer OTA URLs with one-byte HTTPS requests."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import time
import urllib.error
import urllib.request

BASE = Path(__file__).resolve().parent
TAIL = '/component-ota/23/08/14/4f1a650f088f4be39da1e6103015aa24.zip'
PREFIX = '/remove-59822b61319727ba9ca6f2fd62dc0ef2'
HOSTS = ('gauss-compotacostauto-cn.allawnfs.com', 'gauss-opexcostmanual-cn.allawnfs.com',
         'gauss-otacostauto-cn.allawnfs.com', 'gauss-opexcostauto-cn.allawnfs.com',
         'dfs-serverauto-cn.allawnfs.com', 'gauss-cdnctrltrialauto-cn.allawnfs.com',
         'gauss-cdnctrltrialmanual-cn.allawnfs.com', 'componentota-auto-cn.allawnfs.com')
urls = ['https://' + host + ('' if host.startswith('componentota') else PREFIX) + TAIL
        for host in HOSTS]
# The obsolete remove-prefix is also tested separately as a URL hypothesis.
urls += ['https://' + host + TAIL for host in HOSTS if not host.startswith('componentota')]


def probe(url):
    started = time.monotonic()
    result = {'url': url, 'checked_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}
    try:
        request = urllib.request.Request(url, headers={
            'Range': 'bytes=0-0', 'Accept-Encoding': 'identity'})
        with urllib.request.urlopen(request, timeout=10) as response:
            result.update(status=response.status, content_range=response.headers.get('Content-Range'),
                          final_url=response.url, first_byte_hex=response.read(1).hex())
    except urllib.error.HTTPError as error:
        result.update(status=error.code, error=str(error))
    except Exception as error:
        result['error'] = str(error)
    result['elapsed_seconds'] = round(time.monotonic() - started, 2)
    print(json.dumps(result), flush=True)
    return result


with ThreadPoolExecutor(max_workers=4) as executor:
    results = list(executor.map(probe, urls))
report = {'phone_contacted': False, 'max_response_bytes_read_per_url': 1,
          'results': results, 'firmware_downloaded': False}
(BASE / 'docs/august-mirror-availability.json').write_text(json.dumps(report, indent=2) + '\n')
