"""Wait for our download, then validate the complete ZIP and payload hash."""
import base64
import hashlib
import json
from pathlib import Path
import time
import zipfile

BASE = Path(__file__).resolve().parent
directory = BASE.parent / 'downloads'
status_path = directory / 'august-eu-parallel-download.json'
result_path = directory / 'august-eu-ota-integrity.json'
metadata_dir = BASE / 'artifacts/stock-cph2493-August-eu-ota'
result = {'state': 'waiting-for-download', 'phone_contacted': False,
          'whole_archive_integrity_verified': False, 'flash_eligible': False}
result_path.write_text(json.dumps(result, indent=2) + '\n')
deadline = time.monotonic() + 5400
try:
    while time.monotonic() < deadline:
        status = json.loads(status_path.read_text())
        if status['state'] == 'failed':
            raise ValueError('Download failed: ' + str(status['error']))
        if status['state'] == 'download-complete-unverified':
            break
        time.sleep(5)
    else:
        raise TimeoutError('Download deadline exceeded')
    path = Path(status['destination'])
    if not path.resolve().is_relative_to(directory) or path.stat().st_size != status['archive_bytes']:
        raise ValueError('Wrong download path or size')
    cursor = 0
    with path.open('rb') as stream:
        for chunk in status['chunks']:
            if chunk['offset'] != cursor:
                raise ValueError('Download ranges leave holes or overlap')
            data = stream.read(chunk['bytes'])
            if len(data) != chunk['bytes'] or hashlib.sha256(data).hexdigest() != chunk['sha256']:
                raise ValueError('Local range hash mismatch')
            cursor += len(data)
    if cursor != status['archive_bytes']:
        raise ValueError('Download ranges do not cover the archive')
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        while data := stream.read(8 * 1024 * 1024):
            digest.update(data)
    result.update(state='verifying', archive_sha256=digest.hexdigest(), archive_bytes=cursor)
    result_path.write_text(json.dumps(result, indent=2) + '\n')
    with zipfile.ZipFile(path) as archive:
        if archive.testzip() is not None:
            raise ValueError('Archive member CRC mismatch')
        properties_data = archive.read('payload_properties.txt')
        if properties_data != (metadata_dir / 'payload_properties.txt').read_bytes():
            raise ValueError('Properties differ from inspected server copy')
        metadata_data = archive.read('META-INF/com/android/metadata')
        if metadata_data != (metadata_dir / 'metadata.txt').read_bytes():
            raise ValueError('Metadata differs from inspected server copy')
        properties = dict(line.split('=', 1) for line in properties_data.decode().splitlines())
        payload_digest = hashlib.sha256()
        count = 0
        with archive.open('payload.bin') as stream:
            while data := stream.read(8 * 1024 * 1024):
                count += len(data)
                payload_digest.update(data)
        if count != int(properties['FILE_SIZE']) or payload_digest.digest() != base64.b64decode(properties['FILE_HASH'], validate=True):
            raise ValueError('Whole payload size or SHA-256 mismatch')
    final_path = directory / 'CPH2493_13.1.0.561_230814-eu-ota.zip'
    if final_path.exists():
        raise ValueError('Preserve existing final ZIP; refuse to replace it')
    path.rename(final_path)
    result.update(state='verified', archive=str(final_path), whole_archive_integrity_verified=True,
                  all_zip_member_crcs_passed=True, all_download_ranges_verified=True,
                  payload_sha256=payload_digest.hexdigest(), payload_hash_matches_properties=True,
                  publisher_key_independently_trusted=False,
                  completed_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                  limits='Transport/content integrity verified; this does not establish a tested phone restoration path.')
    result_path.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2), flush=True)
except Exception as error:
    result.update(state='failed', error=str(error))
    result_path.write_text(json.dumps(result, indent=2) + '\n')
    raise
