"""Bounded HTTPS range inspection of a stock OTA; never contacts the phone."""
import hashlib
import argparse
import io
import json
from pathlib import Path
import re
import urllib.request
import zipfile
from urllib.parse import urlparse

BASE = Path(__file__).resolve().parent
OUT = BASE / 'artifacts/stock-cph2493-August-ota'
URL = 'https://component-ota-afs.coloros.com/component-ota/23/08/14/4f1a650f088f4be39da1e6103015aa24.zip'


class RemoteRange(io.RawIOBase):
    def __init__(self, url):
        self.url = url
        self.position = 0
        self.transferred = 0
        self.requests = 0
        self.size = None
        self.fetch(0, 1)

    def fetch(self, start, length):
        if not 0 < length <= 16 * 1024 * 1024:
            raise ValueError('Range exceeds bounded read limit')
        if self.transferred + length > 512 * 1024 * 1024:
            raise ValueError('Inspection transfer budget exhausted')
        request = urllib.request.Request(self.url, headers={
            'Range': f'bytes={start}-{start + length - 1}', 'Accept-Encoding': 'identity'})
        with urllib.request.urlopen(request, timeout=20) as response:
            if response.status != 206:
                raise ValueError(f'Server must honor ranges; status {response.status}')
            content_range = response.headers.get('Content-Range', '')
            match = re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)', content_range)
            if not match or int(match[1]) != start or int(match[2]) != start + length - 1:
                raise ValueError('Unexpected content range')
            if self.size is not None and self.size != int(match[3]):
                raise ValueError('Remote size changed')
            self.size = int(match[3])
            data = response.read(length + 1)
            if len(data) != length:
                raise ValueError('Unexpected response length')
        self.transferred += length
        self.requests += 1
        return data

    def seekable(self):
        return True

    def readable(self):
        return True

    def tell(self):
        return self.position

    def seek(self, offset, whence=0):
        target = offset if whence == 0 else self.position + offset if whence == 1 else self.size + offset
        if not 0 <= target <= self.size:
            raise ValueError('Seek outside archive')
        self.position = target
        return target

    def read(self, size=-1):
        length = min(self.size - self.position, size if size >= 0 else self.size)
        if length == 0:
            return b''
        data = self.fetch(self.position, length)
        self.position += length
        return data


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', choices=('component-ota-afs.coloros.com',
        'gauss-componentotacostmanual-cn.allawnfs.com',
        'gauss-otacostmanual-cn.allawnfs.com', 'componentota-manual-cn.allawnfs.com'),
        default='component-ota-afs.coloros.com')
    parser.add_argument('--url', help='Explicit HTTPS archive URL')
    parser.add_argument('--output-name', default='stock-cph2493-August-ota')
    args = parser.parse_args()
    host = args.host
    prefix = '/remove-59822b61319727ba9ca6f2fd62dc0ef2' if host.startswith('gauss-') else ''
    url = f'https://{host}{prefix}/component-ota/23/08/14/4f1a650f088f4be39da1e6103015aa24.zip'
    if args.url:
        parsed_url = urlparse(args.url)
        if parsed_url.scheme != 'https' or not parsed_url.hostname or parsed_url.username or parsed_url.password:
            raise ValueError('Expected public HTTPS archive URL')
        url = args.url
    if not re.fullmatch(r'[A-Za-z0-9_-]+', args.output_name):
        raise ValueError('Output must be a simple artifact name')
    output = BASE / 'artifacts' / args.output_name
    output.mkdir(exist_ok=True)
    stream = RemoteRange(url)
    with zipfile.ZipFile(stream) as archive:
        members = [{'name': item.filename, 'bytes': item.file_size,
                    'compressed_bytes': item.compress_size, 'method': item.compress_type,
                    'header_offset': item.header_offset} for item in archive.infolist()]
        saved = []
        for name in ('META-INF/com/android/metadata', 'payload_properties.txt'):
            item = archive.getinfo(name)
            if item.file_size > 65536 or item.compress_size > 65536:
                raise ValueError('Unexpectedly large metadata')
            data = archive.read(item)
            target = output / ('metadata.txt' if name.endswith('/metadata') else name)
            target.write_bytes(data)
            saved.append({'archive_name': name, 'file': target.name,
                          'sha256': hashlib.sha256(data).hexdigest(),
                          'text': data.decode()})
    report = {'url': url, 'archive_bytes': stream.size, 'transferred_bytes': stream.transferred,
              'requests': stream.requests, 'members': members, 'saved': saved,
              'phone_contacted': False, 'publisher_signature_verified': False,
              'flash_eligible': False}
    (output / 'remote-inspection.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
