"""Download this exact OTA by validated ranges; preserve the original partial."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import time
import urllib.request

BASE = Path(__file__).resolve().parent
REFERENCE = BASE / 'artifacts/stock-cph2493-August-eu-ota/remote-inspection.json'
reference = json.loads(REFERENCE.read_text())
url, total = reference['url'], reference['archive_bytes']
directory = BASE.parent / 'downloads'
destination = directory / 'CPH2493_13.1.0.561_230814-eu-ota.parallel.part'
report_path = directory / 'august-eu-parallel-download.json'
chunk_size = 8 * 1024 * 1024
parser = argparse.ArgumentParser()
parser.add_argument('--resume', action='store_true', help='Resume only after verifying saved range hashes')
args = parser.parse_args()
if destination.exists() and not args.resume:
    raise SystemExit('Preserve existing parallel partial; refuse to overwrite')
if shutil.disk_usage(directory).free < total + 512 * 1024 * 1024:
    raise SystemExit('Insufficient free disk space')
with urllib.request.urlopen(urllib.request.Request(url, headers={'Range': 'bytes=0-0'}), timeout=20) as response:
    if response.status != 206 or response.headers.get('Content-Range') != f'bytes 0-0/{total}':
        raise ValueError('Server no longer honors ranges or size changed')
    etag = response.headers.get('ETag')
    response.read(1)
if args.resume:
    saved = json.loads(report_path.read_text())
    if saved['url'] != url or saved['archive_bytes'] != total or saved['etag'] != etag:
        raise ValueError('Saved download describes a different object')
    fd = os.open(destination, os.O_RDWR)
    if os.fstat(fd).st_size != total:
        raise ValueError('Saved partial file size changed')
else:
    fd = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
    os.ftruncate(fd, total)
started = time.monotonic()
completed = []
if args.resume:
    offsets_seen = set()
    for item in saved['chunks']:
        start, length = item['offset'], item['bytes']
        if start in offsets_seen or start < 0 or start % chunk_size or length != min(chunk_size, total - start) or length <= 0:
            raise ValueError('Invalid saved range record')
        offsets_seen.add(start)
        data = os.pread(fd, length, start)
        if len(data) == length and hashlib.sha256(data).hexdigest() == item['sha256']:
            completed.append(item)
    print('Validated saved ranges:', len(completed), flush=True)


def download_chunk(start):
    length = min(chunk_size, total - start)
    headers = {'Range': f'bytes={start}-{start + length - 1}', 'Accept-Encoding': 'identity'}
    if etag:
        headers['If-Match'] = etag
    for attempt in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as response:
                if response.status != 206 or response.headers.get('Content-Range') != f'bytes {start}-{start + length - 1}/{total}':
                    raise ValueError('Wrong range response')
                if etag and response.headers.get('ETag') != etag:
                    raise ValueError('Remote object changed')
                data = response.read(length + 1)
                if len(data) != length:
                    raise ValueError('Truncated or oversized range')
            written = 0
            while written < length:
                count = os.pwrite(fd, data[written:], start + written)
                if count <= 0:
                    raise OSError('Failed to write range')
                written += count
            return {'offset': start, 'bytes': length, 'sha256': hashlib.sha256(data).hexdigest()}
        except Exception:
            if attempt == 2:
                raise
            time.sleep(0.5 * (attempt + 1))


def record(state, error=None):
    elapsed = time.monotonic() - started
    transferred = sum(item['bytes'] for item in completed)
    report = {'url': url, 'destination': str(destination), 'archive_bytes': total,
              'etag': etag, 'state': state, 'completed_bytes': transferred,
              'elapsed_seconds': round(elapsed, 2),
              'mib_per_second': round(transferred / 1024 ** 2 / max(elapsed, 0.001), 2),
              'chunks': sorted(completed, key=lambda item: item['offset']),
              'archive_integrity_verified': False, 'phone_contacted': False,
              'error': error}
    temporary = report_path.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(report, indent=2) + '\n')
    temporary.replace(report_path)
    print(f'{state}: {transferred}/{total} bytes, {report["mib_per_second"]} MiB/s', flush=True)


try:
    record('downloading')
    last_report = started
    with ThreadPoolExecutor(max_workers=8) as executor:
        done_offsets = {item['offset'] for item in completed}
        pending = [executor.submit(download_chunk, start) for start in range(0, total, chunk_size) if start not in done_offsets]
        for future in as_completed(pending):
            completed.append(future.result())
            if time.monotonic() - last_report > 10:
                record('downloading')
                last_report = time.monotonic()
    os.fsync(fd)
    record('download-complete-unverified')
except Exception as error:
    record('failed', str(error))
    raise
finally:
    os.close(fd)
