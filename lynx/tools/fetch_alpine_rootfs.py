"""Fetch a pinned official ARM64 mini-rootfs and verify its release signature."""
import argparse
import concurrent.futures
import hashlib
import json
import os
import subprocess
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSION = '3.24.2'
NAME = 'alpine-minirootfs-' + VERSION + '-aarch64.tar.gz'
BASE = 'https://dl-cdn.alpinelinux.org/alpine/v3.24/releases/aarch64/'
FINGERPRINT = '0482D84022F52DF1C4E7CD43293ACD0907D9495A'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--download', action='store_true')
    args = parser.parse_args()
    if not args.download:
        print('Use --download to fetch and verify official Alpine ARM64 ' + VERSION + '. No phone contact.')
        return
    os.umask(0o077)
    out = ROOT / 'downloads' / ('alpine-rootfs-' + VERSION + '-' + str(time.time_ns()))
    out.mkdir(mode=0o700)
    report = {'started_ns': time.time_ns(), 'version': VERSION, 'architecture': 'aarch64',
              'expected_primary_fingerprint': FINGERPRINT,
              'trust_anchor': 'Fingerprint published at https://www.alpinelinux.org/downloads/',
              'downloads': [], 'operations': [], 'passed': False, 'phone_contacted': False}

    def save():
        (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')

    def fetch(item):
        name, url = item
        record = {'name': name, 'url': url, 'started_ns': time.time_ns()}
        try:
            with urllib.request.urlopen(url, timeout=35) as response:
                raw = response.read(32 * 1024 * 1024 + 1)
                if len(raw) > 32 * 1024 * 1024:
                    raise ValueError('Download size cap exceeded')
                (out / name).write_bytes(raw)
                record.update(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(),
                              response_headers=dict(response.headers), final_url=response.url)
        except Exception as error:
            record['error'] = str(error)
        record['finished_ns'] = time.time_ns()
        return record

    def run(name, arguments):
        started = time.time_ns()
        process = subprocess.run(['gpg', '--no-options', '--homedir', str(out / 'gnupg'),
                                  '--batch', '--no-auto-key-retrieve', *arguments],
                                 capture_output=True, timeout=25)
        (out / (name + '.stdout')).write_bytes(process.stdout)
        (out / (name + '.stderr')).write_bytes(process.stderr)
        report['operations'].append({'name': name, 'started_ns': started, 'finished_ns': time.time_ns(),
                                     'exit_code': process.returncode,
                                     'stdout_sha256': hashlib.sha256(process.stdout).hexdigest()})
        save()
        if process.returncode:
            raise ValueError(name + ' failed; see retained GPG captures')
        return process.stdout.decode()

    try:
        items = [(NAME + suffix, BASE + NAME + suffix) for suffix in ['', '.sha256', '.sha512', '.asc']]
        items.append(('ncopa.asc', 'https://www.alpinelinux.org/keys/ncopa.asc'))
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
            report['downloads'] = list(pool.map(fetch, items))
        save()
        if any('error' in record for record in report['downloads']):
            raise ValueError('A download failed; all partial results retained')
        raw = (out / NAME).read_bytes()
        for algorithm in ['sha256', 'sha512']:
            expected, filename = (out / (NAME + '.' + algorithm)).read_text().split()
            if filename.lstrip('*') != NAME or hashlib.new(algorithm, raw).hexdigest() != expected:
                raise ValueError(algorithm + ' mismatch')
        (out / 'gnupg').mkdir(mode=0o700)
        listing = run('key-list', ['--with-colons', '--import-options', 'show-only', '--import', str(out / 'ncopa.asc')])
        primaries, awaiting_primary = [], False
        for line in listing.splitlines():
            fields = line.split(':')
            if fields[0] == 'pub':
                awaiting_primary = True
            elif fields[0] == 'sub':
                awaiting_primary = False
            elif fields[0] == 'fpr' and awaiting_primary:
                primaries.append(fields[9]); awaiting_primary = False
        if primaries != [FINGERPRINT]:
            raise ValueError('Release public key primary fingerprint mismatch')
        run('key-import', ['--import', str(out / 'ncopa.asc')])
        status = run('signature', ['--status-fd', '1', '--verify', str(out / (NAME + '.asc')), str(out / NAME)])
        valid = [line.split() for line in status.splitlines() if line.startswith('[GNUPG:] VALIDSIG ')]
        if not any(FINGERPRINT in line[2:] for line in valid):
            raise ValueError('Expected release signature missing')
        report.update(passed=True, sha256=hashlib.sha256(raw).hexdigest(),
                      sha512=hashlib.sha512(raw).hexdigest(), signature_verified=True,
                      archive=str(out / NAME), primary_fingerprint=FINGERPRINT)
    except Exception as error:
        report['error'] = str(error)
    report['finished_ns'] = time.time_ns(); save()
    print(json.dumps({'passed': report['passed'], 'result': str(out / 'result.json')}))
    if not report['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
