"""Export only the exact diagnostic packages proven in a successful offline VM."""
import argparse
import hashlib
import io
import json
import os
import tarfile
import time
from pathlib import Path, PurePosixPath

from alpine_rootfs import ROOT, ARCHIVE_SHA256


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--vm-receipt', type=Path, required=True)
    parser.add_argument('--cache-receipt', type=Path, required=True)
    args = parser.parse_args()
    vm = json.loads(args.vm_receipt.read_text())
    console = args.vm_receipt.with_name('console.log').read_bytes()
    if not (vm.get('passed') and vm['checks'].get('offline_install_and_trace')
            and vm['inventory']['archive_sha256'] == ARCHIVE_SHA256
            and hashlib.sha256(console).hexdigest() == vm['console_sha256']):
        raise ValueError('Successful matching offline VM evidence required')
    expected = {item['name']: item['sha256'] for item in vm['offline_packages']}
    if len(expected) != 7:
        raise ValueError('Unexpected diagnostic package count')
    receipt = json.loads(args.cache_receipt.read_text())
    operation = next(op for op in receipt['operations'] if op['name'] == 'command')
    cache = args.cache_receipt.with_name('command.stdout')
    if not (receipt.get('native_identity_verified') and operation['exit_code'] == 0
            and hashlib.sha256(cache.read_bytes()).hexdigest() == operation['stdout_sha256']):
        raise ValueError('Verified cache capture required')
    packages = {}
    with tarfile.open(cache, 'r:gz') as source:
        for member in source:
            name = PurePosixPath(member.name).name
            if member.isfile() and name in expected:
                if name in packages or member.size > 16 * 1024 * 1024:
                    raise ValueError('Duplicate/oversized package')
                data = source.extractfile(member).read()
                if hashlib.sha256(data).hexdigest() != expected[name]:
                    raise ValueError('VM-proven package changed')
                packages[name] = data
    if packages.keys() != expected.keys():
        raise ValueError('Incomplete package set')
    os.umask(0o077)
    out = ROOT / 'linux-port/artifacts' / ('alpine-offline-diagnostics-' + str(time.time_ns()))
    out.mkdir(mode=0o700)
    bundle = out / 'diagnostic-apks.tar.gz'
    with tarfile.open(bundle, 'w:gz') as target:
        for name, data in sorted(packages.items()):
            member = tarfile.TarInfo('lynx-offline-apks/' + name)
            member.mode = 0o600; member.size = len(data); member.mtime = 0
            target.addfile(member, io.BytesIO(data))
    with tarfile.open(bundle, 'r:gz') as archive:
        roundtrip = {PurePosixPath(item.name).name: hashlib.sha256(archive.extractfile(item).read()).hexdigest()
                     for item in archive if item.isfile()}
    if roundtrip != expected:
        raise ValueError('Bundle round trip failed')
    report = {'passed': True, 'bundle': str(bundle), 'sha256': hashlib.sha256(bundle.read_bytes()).hexdigest(),
              'packages': expected, 'base_rootfs_sha256': ARCHIVE_SHA256,
              'vm_receipt': str(args.vm_receipt.resolve()), 'cache_receipt': str(args.cache_receipt.resolve()),
              'phone_contacted': False, 'limits': 'Exact VM-proven APK bytes; install with standard signature verification.'}
    (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'passed': True, 'result': str(out / 'result.json')}))


if __name__ == '__main__':
    main()
