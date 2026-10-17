"""Verify and bundle the exact signed ARM64 Alpine OpenRC APKs kept locally."""
import hashlib
import json
import subprocess
import tarfile
import time
import io
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / 'linux-port/artifacts/openrc-package-preparation'
RUNTIME = ROOT / 'linux-port/artifacts/openrc-runtime-root'
PACKAGES = {
    'bridge': ('1.5-r5', 'bridge-1.5-r5.63b8b1dc.apk'),
    'ifupdown-ng': ('0.13.0-r0', 'ifupdown-ng-0.13.0-r0.def1162f.apk'),
    'libcap2': ('2.78-r0', 'libcap2-2.78-r0.0fb65b85.apk'),
    'openrc': ('0.63.2-r0', 'openrc-0.63.2-r0.cbfec59e.apk'),
    'openrc-init': ('0.63.2-r0', 'openrc-init-0.63.2-r0.5557b43b.apk'),
    'openrc-user': ('0.63.2-r0', 'openrc-user-0.63.2-r0.a4bc2a78.apk'),
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify-existing', action='store_true')
    args = parser.parse_args()
    apk = WORK / 'apk.static-3.0.8'
    keys = RUNTIME / 'etc/apk/keys'
    cache = RUNTIME / 'var/cache/apk'
    files = {}
    for package, (version, filename) in PACKAGES.items():
        path = cache / filename
        data = path.read_bytes()
        result = subprocess.run([str(apk), '--root', str(RUNTIME), '--keys-dir', str(keys),
                                 'verify', str(path)], check=True, capture_output=True, text=True)
        if result.stdout.strip() != str(path) + ': OK':
            raise ValueError(f'Unexpected APK verifier output for {package}')
        if not filename.startswith(package + '-' + version + '.'):
            raise ValueError(f'Package path/version mismatch: {filename}')
        files[filename] = {'package': package, 'version': version,
                           'bytes': len(data), 'sha256': sha(data),
                           'signature_verified': True}

    archive_path = WORK / 'openrc-apks.tar.gz'
    receipt_path = WORK / 'openrc-apks.json'
    if args.verify_existing:
        if not archive_path.is_file() or not receipt_path.is_file():
            raise SystemExit('Existing OpenRC bundle evidence is incomplete')
        old = json.loads(receipt_path.read_text())
        if old.get('packages') != files:
            raise ValueError('Existing OpenRC bundle package inventory differs')
    elif archive_path.exists() or receipt_path.exists():
        raise SystemExit('Refusing to overwrite existing OpenRC bundle evidence')
    else:
        with tarfile.open(archive_path, 'w:gz', compresslevel=9) as archive:
            for filename in sorted(files):
                info = tarfile.TarInfo('openrc-apks/' + filename)
                info.mode = 0o600
                info.size = files[filename]['bytes']
                with (cache / filename).open('rb') as stream:
                    archive.addfile(info, stream)
    bundle = archive_path.read_bytes()
    seen = {}
    with tarfile.open(fileobj=io.BytesIO(bundle), mode='r:gz') as archive:
        for member in archive:
            if (not member.isfile() or member.name.startswith('/') or '..' in Path(member.name).parts
                    or member.name != 'openrc-apks/' + Path(member.name).name):
                raise ValueError('Unexpected member in OpenRC bundle')
            data = archive.extractfile(member).read()
            filename = Path(member.name).name
            if filename in seen or len(data) != member.size:
                raise ValueError('Duplicate or truncated OpenRC APK in bundle')
            seen[filename] = sha(data)
    if seen != {filename: item['sha256'] for filename, item in files.items()}:
        raise ValueError('OpenRC package bundle round-trip hash mismatch')
    if args.verify_existing:
        if old.get('bundle_sha256') != sha(bundle) or old.get('bundle_bytes') != len(bundle):
            raise ValueError('Existing OpenRC bundle receipt does not match archive')
        print(json.dumps({'state': 'signed-openrc-bundle-verified',
                          'bundle': str(archive_path), 'bundle_sha256': sha(bundle),
                          'packages': sorted(files)}))
        return
    receipt = {'state': 'signed-openrc-bundle-verified', 'created_ns': time.time_ns(),
               'source': 'verified local Alpine v3.24 aarch64 repository package cache',
               'apk_tools': '3.0.8-r0', 'packages': files,
               'bundle': str(archive_path), 'bundle_bytes': len(bundle),
               'bundle_sha256': sha(bundle), 'network_used': False,
               'signature_override_used': False, 'phone_contacted': False}
    receipt_path.write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps({'state': receipt['state'], 'bundle': str(archive_path),
                      'bundle_sha256': receipt['bundle_sha256'],
                      'packages': sorted(files)}))


if __name__ == '__main__':
    main()
