"""Read-only summary of Lynx's preserved OTA download and verification reports."""
import json
from pathlib import Path

root = Path(__file__).resolve().parent.parent
directory = root / 'downloads'
download = json.loads((directory / 'august-eu-parallel-download.json').read_text())
integrity = json.loads((directory / 'august-eu-ota-integrity.json').read_text())
signature_file = directory / 'august-eu-payload-signature.json'
signature = json.loads(signature_file.read_text()) if signature_file.exists() else {'state': 'not-started'}
total = download['archive_bytes']
complete = download['completed_bytes']
rate = download['mib_per_second'] * 1024 ** 2
report = {'device': 'Lynx / CPH2493', 'download_state': download['state'],
          'download_percent': round(100 * complete / total, 1),
          'downloaded_bytes': complete, 'archive_bytes': total,
          'estimated_minutes_remaining': round((total - complete) / rate / 60, 1) if rate else None,
          'whole_archive_integrity_state': integrity['state'],
          'whole_payload_signature_state': signature['state'],
          'archive': integrity.get('archive'),
          'error': download.get('error') or integrity.get('error') or signature.get('error'),
          'phone_contacted': False}
print(json.dumps(report, indent=2))
