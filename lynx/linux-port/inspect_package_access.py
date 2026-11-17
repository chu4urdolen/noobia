"""Inspect the user-provided public download endpoints; no login or purchase."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import html
import json
from pathlib import Path
import re
import urllib.error
import urllib.request

BASE = Path(__file__).resolve().parent
OUT = BASE / 'artifacts/august-package-access'
OUT.mkdir(exist_ok=True)
endpoints = {
    'romdevelopers': 'https://romdevelopers.com/index.php?a=downloads&b=file&c=download&id=158830',
    'firmwaredrive': 'https://firmwaredrive.com/index.php?a=downloads&b=file&c=download&id=125242',
}


def inspect(item):
    label, url = item
    report = {'provider': label, 'requested_url': url, 'credentials_supplied': False,
              'purchase_attempted': False, 'archive_verified': False}
    try:
        with urllib.request.urlopen(url, timeout=20) as response:
            report.update(status=response.status, final_url=response.url,
                          content_type=response.headers.get('Content-Type'),
                          content_length=response.headers.get('Content-Length'))
            prefix = response.read(65536)
            report['prefix_sha256'] = hashlib.sha256(prefix).hexdigest()
            report['zip_magic_observed'] = prefix.startswith(b'PK\x03\x04')
            if report['zip_magic_observed']:
                (OUT / (label + '-download-prefix.bin')).write_bytes(prefix)
            else:
                (OUT / (label + '-download-response.html')).write_bytes(prefix)
                page = prefix.decode(errors='replace')
                page = re.sub(r'<(script|style)\b[^>]*>.*?</\1>', '', page, flags=re.S | re.I)
                visible = html.unescape(re.sub(r'<[^>]+>', ' ', page))
                visible = re.sub(r'\s+', ' ', visible).strip()
                report['visible_response'] = visible[:10000]
    except urllib.error.HTTPError as error:
        report.update(status=error.code, error=str(error))
    except Exception as error:
        report['error'] = str(error)
    return report


with ThreadPoolExecutor(max_workers=2) as executor:
    results = list(executor.map(inspect, endpoints.items()))
report = {'phone_contacted': False, 'package_obtained': False, 'flash_eligible': False,
          'endpoints': results}
(OUT / 'access-report.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
