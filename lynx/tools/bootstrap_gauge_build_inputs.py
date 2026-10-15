"""Fetch pinned official build inputs locally; never access the handset."""
import argparse
import hashlib
import json
import os
import subprocess
import tarfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GOOGLE = 'https://android.googlesource.com/platform/prebuilts/clang/host/linux-x86'
KERNEL = '81ec42ad5e803be0cba619f9f7bb298db7d33d7b'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--full-kernel-archive', action='store_true', help='Optional slow full archive; prefer a pinned sparse checkout for an external module')
    args = parser.parse_args()
    os.umask(0o077)
    out = ROOT / 'tools' / ('gauge-build-inputs-' + str(time.time_ns()))
    out.mkdir(mode=0o700)
    report = {'phone_contacted': False, 'sources': [], 'started_ns': time.time_ns()}
    receipt = out / 'result.json'

    def save():
        temporary = receipt.with_suffix('.tmp')
        temporary.write_text(json.dumps(report, indent=2) + '\n')
        temporary.replace(receipt)

    save()
    try:
        with urllib.request.urlopen(GOOGLE + '/+/refs/heads/android12-release?format=JSON', timeout=30) as response:
            raw = response.read(1024 * 1024)
        (out / 'official-compiler-commit.json').write_bytes(raw)
        commit = json.loads(raw.decode().split('\n', 1)[1])['commit']
        specs = [('clang', GOOGLE + '/+archive/' + commit + '/clang-r416183b.tar.gz')]
        if args.full_kernel_archive:
            specs.append(('kernel', 'https://codeload.github.com/OnePlusOSS/android_kernel_5.10_oneplus_mt6983/tar.gz/' + KERNEL))
        for name, url in specs:
            row = {'name': name, 'url': url, 'state': 'downloading'}
            report['sources'].append(row)
            save()
            partial = out / (name + '.tar.gz.partial')
            digest = hashlib.sha256()
            total = 0
            with urllib.request.urlopen(url, timeout=60) as response, partial.open('xb') as stream:
                row['resolved_url'] = response.url
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > 2 * 1024 ** 3:
                        raise ValueError('Archive exceeds 2 GiB bound')
                    stream.write(chunk)
                    digest.update(chunk)
                    row['downloaded_bytes'] = total
                    row['heartbeat_ns'] = time.time_ns()
                    save()
            archive = partial.with_suffix('')
            partial.rename(archive)
            row.update(state='downloaded', sha256=digest.hexdigest(), archive=str(archive))
            save()
            destination = out / name
            destination.mkdir(mode=0o700)
            # Python's data filter rejects traversal, escaping links, devices,
            # and unsafe permissions. Extract only into this new owned tree.
            with tarfile.open(archive, 'r:gz') as contents:
                contents.extractall(destination, filter='data')
            row.update(state='extracted', destination=str(destination))
            if name == 'clang':
                check = subprocess.run([str(destination / 'bin/clang'), '--version'],
                                       capture_output=True, timeout=15)
                (out / 'clang-version.stdout').write_bytes(check.stdout)
                (out / 'clang-version.stderr').write_bytes(check.stderr)
                text = check.stdout.decode(errors='replace')
                if check.returncode or not all(x in text for x in ['12.0.5', 'r416183b', '7284624']):
                    raise ValueError('Compiler identity differs from exact OEM configuration')
                row['compiler_identity_verified'] = True
            save()
        report.update(state='inputs-prepared', finished_ns=time.time_ns(),
                      limits='Build inputs only. No module has been built, validated, or loaded.')
    except Exception as error:
        report.update(state='failed', error=str(error), finished_ns=time.time_ns())
        save()
        raise
    save()
    print(json.dumps({'result': str(receipt), 'state': report['state']}, indent=2), flush=True)


if __name__ == '__main__':
    main()
