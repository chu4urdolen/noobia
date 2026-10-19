"""Build a host-only 1 GiB Alpine/OpenRC ext4 root image; never contact Lynx."""
import gzip
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import tarfile
import time


ROOT = Path(__file__).resolve().parent.parent
CHECKPOINT = ROOT / 'checkpoints/alpine-runtime-1792331453858559525'
BUNDLE = ROOT / 'linux-port/artifacts/openrc-package-preparation/openrc-apks.tar.gz'
BUNDLE_RECEIPT = BUNDLE.parent / 'openrc-apks.json'
APK = ROOT / 'linux-port/artifacts/openrc-package-preparation/apk.static-3.0.8'
APK_SHA = '5118a57ae7c07e13268a754f78aa9c7d39a0bed708bb11c101d78e2a884cee5d'
SIZE = 1 << 30


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def call(args, *, timeout=120):
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f'{args[0]} failed ({result.returncode}): '
                           + result.stderr[-1000:])
    return result.stdout


def main():
    if os.geteuid() != 0:
        raise SystemExit('Run as root for numeric archive ownership and ext4 image creation')
    checkpoint = json.loads((CHECKPOINT / 'result.json').read_text())
    archive = CHECKPOINT / 'rootfs.tar.gz'
    receipt = json.loads(BUNDLE_RECEIPT.read_text())
    if (checkpoint.get('state') != 'checkpoint-verified' or
            checkpoint.get('archive_sha256') != sha(archive) or
            checkpoint.get('archive_bytes') != archive.stat().st_size or
            receipt.get('state') != 'signed-openrc-bundle-verified' or
            receipt.get('bundle_sha256') != sha(BUNDLE) or
            sha(APK) != APK_SHA):
        raise ValueError('Verified Alpine/OpenRC inputs changed')
    os.umask(0o077)
    out = ROOT / 'linux-port/artifacts' / ('persistent-alpine-ext4-' + str(time.time_ns()))
    out.mkdir(mode=0o700)
    staging = out / 'rootfs-staging'
    staging.mkdir(mode=0o700)
    report = {'state': 'starting', 'created_ns': time.time_ns(),
              'phone_contacted': False, 'phone_partition_writes': False,
              'checkpoint_sha256': checkpoint['archive_sha256'],
              'openrc_bundle_sha256': receipt['bundle_sha256'],
              'image_bytes': SIZE, 'staging': str(staging)}

    def save():
        temporary = out / 'result.tmp'
        temporary.write_text(json.dumps(report, indent=2) + '\n')
        temporary.replace(out / 'result.json')

    save()
    try:
        with tarfile.open(archive, 'r:gz') as source:
            members = source.getmembers()
            kinds = {}
            for member in members:
                path = PurePosixPath(member.name)
                if (path.is_absolute() or '..' in path.parts or
                        not (member.isfile() or member.isdir() or member.issym())):
                    raise ValueError('Unsafe checkpoint member')
                normalized = str(path).removeprefix('./')
                if normalized in kinds:
                    raise ValueError('Duplicate checkpoint member')
                kinds[normalized] = member
            for name in kinds:
                for parent in PurePosixPath(name).parents:
                    if str(parent) == '.':
                        continue
                    ancestor = kinds.get(str(parent))
                    if ancestor is not None and not ancestor.isdir():
                        raise ValueError('Checkpoint member below a non-directory')
            # Absolute links are needed inside Alpine, but no archive member may
            # be extracted through one of those links on the host.
            source.extractall(staging, filter='tar')
        if (staging / 'etc/alpine-release').read_text().strip() != '3.24.2':
            raise ValueError('Alpine version differs')
        cache = staging / 'var/cache/apk'
        cache.mkdir(parents=True, exist_ok=True)
        packages = receipt['packages']
        package_paths = []
        with tarfile.open(fileobj=io.BytesIO(BUNDLE.read_bytes()), mode='r:gz') as source:
            seen = set()
            for member in source:
                name = PurePosixPath(member.name)
                if (not member.isfile() or len(name.parts) != 2 or
                        name.parts[0] != 'openrc-apks' or name.name not in packages or
                        name.name in seen):
                    raise ValueError('Unexpected OpenRC bundle member')
                seen.add(name.name)
                data = source.extractfile(member).read()
                expected = packages[name.name]
                if (len(data) != expected['bytes'] or
                        hashlib.sha256(data).hexdigest() != expected['sha256']):
                    raise ValueError('OpenRC package hash differs')
                path = cache / name.name
                path.write_bytes(data)
                package_paths.append(path)
        if len(package_paths) != len(packages):
            raise ValueError('OpenRC bundle incomplete')
        keys = staging / 'etc/apk/keys'
        for package in package_paths:
            verified = call([str(APK), '--root', str(staging), '--keys-dir',
                             str(keys), 'verify', str(package)])
            if not verified.strip().endswith(': OK'):
                raise ValueError('OpenRC package signature refused')
        report['apk_install_stdout'] = call([
            str(APK), '--root', str(staging), '--arch', 'aarch64',
            '--keys-dir', str(keys), '--repositories-file', '/dev/null',
            '--cache-dir', str(cache), '--no-network', '--no-scripts',
            '--cache-packages', 'add', *map(str, package_paths)], timeout=120)
        for rel in ('sbin/openrc-init', 'sbin/apk', 'usr/bin/python3',
                    'usr/bin/git', 'usr/bin/make'):
            if not (staging / rel).exists():
                raise ValueError('Expected rootfs executable missing: ' + rel)
        (staging / 'etc/hostname').write_text('lynx\n')
        image = out / 'alpine-openrc-root-1GiB.ext4'
        with image.open('wb') as destination:
            destination.truncate(SIZE)
        report['mkfs_stdout'] = call([
            '/usr/sbin/mke2fs', '-t', 'ext4', '-F', '-L', 'LYNXROOT',
            '-E', 'lazy_itable_init=0,lazy_journal_init=0',
            '-d', str(staging), str(image)], timeout=300)
        report['fsck_stdout'] = call(['/usr/sbin/e2fsck', '-fn', str(image)],
                                     timeout=120)
        report['image_sha256'] = sha(image)
        report['image_disk_bytes'] = image.stat().st_blocks * 512
        compressed = out / 'alpine-openrc-root-1GiB.ext4.gz'
        with image.open('rb') as source, compressed.open('wb') as destination:
            with gzip.GzipFile(filename='', mode='wb', fileobj=destination,
                               compresslevel=1, mtime=0) as stream:
                for block in iter(lambda: source.read(1 << 20), b''):
                    stream.write(block)
        report['compressed_sha256'] = sha(compressed)
        report['compressed_bytes'] = compressed.stat().st_size
        restored = hashlib.sha256()
        restored_bytes = 0
        with gzip.open(compressed, 'rb') as source:
            for block in iter(lambda: source.read(1 << 20), b''):
                restored.update(block)
                restored_bytes += len(block)
        if restored_bytes != SIZE or restored.hexdigest() != report['image_sha256']:
            raise ValueError('Compressed image round trip differs')
        report['state'] = 'offline-ext4-root-image-verified'
    except Exception as error:
        report.update(state='failed', error=str(error))
    report['finished_ns'] = time.time_ns()
    save()
    if report['state'] == 'offline-ext4-root-image-verified' and os.environ.get('SUDO_GID'):
        group = int(os.environ['SUDO_GID'])
        os.chown(out, 0, group)
        out.chmod(0o750)
        for path in (out / 'result.json', image, compressed):
            os.chown(path, 0, group)
            path.chmod(0o640)
    print(json.dumps({'state': report['state'], 'result': str(out / 'result.json')}))
    if report['state'] != 'offline-ext4-root-image-verified':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
