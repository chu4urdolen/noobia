"""Bundle validated recovery reference files; no flashing tools or bootloader image."""
import hashlib
import json
from pathlib import Path
import zipfile
import argparse

BASE = Path(__file__).resolve().parent
STOCK = BASE / 'artifacts/stock-cph2493-August-eu-ota'
inspection = json.loads((STOCK / 'package-inspection.json').read_text())
avb = json.loads((BASE / 'docs/august-stock-avb-audit.json').read_text())
recovery = json.loads((BASE / 'docs/august-recovery-audit.json').read_text())
require_names = ('boot.img', 'vendor_boot.img', 'dtbo.img', 'vbmeta.img', 'vbmeta_system.img', 'vbmeta_vendor.img')
parser = argparse.ArgumentParser()
parser.add_argument('--verified-source', action='store_true', help='Include successful full-ZIP and payload-signature verification reports')
args = parser.parse_args()
integrity = signature = None
if args.verified_source:
    integrity = json.loads((BASE.parent / 'downloads/august-eu-ota-integrity.json').read_text())
    signature = json.loads((BASE.parent / 'downloads/august-eu-payload-signature.json').read_text())
    if integrity['state'] != 'verified' or signature['state'] != 'verified' or not signature['full_payload_signature_valid']:
        raise ValueError('Complete source verification has not passed')
hashes = {Path(item['file']).name: item['sha256'] for item in inspection['components']}
if not inspection['reference_lk_build_string_matches_installed']:
    raise ValueError('LK build comparison did not match')
if any(item.get('valid') is False or item.get('embedded_child_key_matches') is False for item in avb['descriptor_checks']):
    raise ValueError('AVB descriptor verification failed')
if any(item.get('metadata_check_passed') is False for item in avb['images'].values()):
    raise ValueError('AVB metadata verification failed')
name = 'lynx-August-recovery-verified-source.zip' if args.verified_source else 'lynx-August-recovery-reference.zip'
output = BASE.parent / 'downloads' / name
if output.exists():
    raise ValueError('Preserve existing reference bundle; refuse to replace it')
components = []
for name in require_names:
    data = (STOCK / name).read_bytes()
    if hashlib.sha256(data).hexdigest() != hashes[name]:
        raise ValueError('Component changed: ' + name)
    components.append({'name': name, 'bytes': len(data), 'sha256': hashes[name]})
manifest = {'name': 'Lynx August recovery reference', 'model': 'CPH2493',
            'version': inspection['stock_version'], 'source_url': inspection['url'],
            'matching_recorded_bootloader': inspection['installed_bootloader'],
            'components': components, 'hardware_restoration_tested': False,
            'whole_source_zip_verification_pending': not args.verified_source,
            'source_zip_sha256': integrity['archive_sha256'] if integrity else None,
            'full_payload_signature_valid': signature['full_payload_signature_valid'] if signature else None,
            'flash_authorized': False,
            'limits': ['These are reference-package images, not on-device backups.',
                      'Offline matching and image integrity do not prove recovery can boot on Lynx.',
                      'This bundle contains no LK/preloader image or flash script.',
                      'Use existing partition layout; no slot switch, GPT alteration or data format.']}
notes = '''Lynx / OnePlus Nord 3 CPH2493

This is a locally assembled reference set from the August 2023 stock OTA,
not an OEM service ZIP and not a native Linux installation image.
Its purpose is to make potential undo/recovery resources concrete and reviewable.
The bootloader build string matches Lynx's recorded identifier; storage writes
and recovery startup have not been tested. There is no automatic flash script.
No Android restore is required before a native Linux trial.

Read MANIFEST.json and the included audits before considering any use.
The full source download has a separate integrity report under downloads/.
The included reports are snapshots of the offline investigation.
'''
with zipfile.ZipFile(output, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=1) as archive:
    archive.writestr('MANIFEST.json', json.dumps(manifest, indent=2) + '\n')
    archive.writestr('README.txt', notes)
    for name in require_names:
        archive.write(STOCK / name, 'images/' + name)
    archive.write(BASE / 'docs/august-stock-avb-audit.json', 'audits/avb.json')
    archive.write(BASE / 'docs/august-recovery-audit.json', 'audits/recovery.json')
    archive.write(STOCK / 'metadata-signature-audit.json', 'audits/ota-metadata-signature.json')
    if args.verified_source:
        archive.write(BASE.parent / 'downloads/august-eu-ota-integrity.json', 'audits/source-package-integrity.json')
        archive.write(BASE.parent / 'downloads/august-eu-payload-signature.json', 'audits/source-payload-signature.json')
with zipfile.ZipFile(output) as archive:
    if archive.testzip() is not None:
        raise ValueError('Reference bundle CRC verification failed')
    for item in components:
        if hashlib.sha256(archive.read('images/' + item['name'])).hexdigest() != item['sha256']:
            raise ValueError('Reference bundle image hash differs')
receipt = {'file': str(output), 'bytes': output.stat().st_size,
           'sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
           'all_bundle_crcs_and_image_hashes_verified': True, 'phone_contacted': False,
           'flash_eligible': False}
(output.parent / (output.stem + '-receipt.json')).write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(receipt, indent=2))
