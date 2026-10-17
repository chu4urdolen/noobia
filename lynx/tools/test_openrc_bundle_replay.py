"""Replay the signed OpenRC bundle from a verified Alpine rootfs, then boot it in QEMU."""
import hashlib
import io
import json
import os
import stat
import subprocess
import tarfile
import time
from pathlib import Path, PurePosixPath

from alpine_rootfs import read_rootfs

ROOT = Path(__file__).resolve().parent.parent
BUNDLE_RECEIPT = ROOT / 'linux-port/artifacts/openrc-package-preparation/openrc-apks.json'
APK = ROOT / 'linux-port/artifacts/openrc-package-preparation/apk.static-3.0.8'
APK_SHA256 = '5118a57ae7c07e13268a754f78aa9c7d39a0bed708bb11c101d78e2a884cee5d'
BASE_RECEIPT = ROOT / 'downloads/alpine-rootfs-3.24.2-1792179591745064903/result.json'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def materialize(entries, target):
    target.mkdir(mode=0o700)
    ordered = sorted(entries.items(), key=lambda pair: (
        not stat.S_ISDIR(pair[1]['mode']), pair[0].count('/'), pair[0]))
    for name, item in ordered:
        path = target / name
        mode = item['mode']
        if stat.S_ISDIR(mode):
            path.mkdir(mode=stat.S_IMODE(mode), parents=True, exist_ok=True)
        elif stat.S_ISREG(mode):
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         stat.S_IMODE(mode))
            with os.fdopen(fd, 'wb') as output:
                output.write(item['data'])
        elif not stat.S_ISLNK(mode):
            raise ValueError('Unsupported base rootfs member: ' + name)
    for name, item in ordered:
        if stat.S_ISLNK(item['mode']):
            os.symlink(item['data'].decode(), target / name)


def main():
    receipt = json.loads(BUNDLE_RECEIPT.read_text())
    bundle_path = Path(receipt['bundle']).resolve(strict=True)
    bundle = bundle_path.read_bytes()
    if (receipt.get('state') != 'signed-openrc-bundle-verified'
            or sha(bundle) != receipt['bundle_sha256'] or sha(APK.read_bytes()) != APK_SHA256):
        raise ValueError('Pinned APK tool or signed OpenRC bundle mismatch')
    packages = receipt['packages']
    members = {}
    with tarfile.open(fileobj=io.BytesIO(bundle), mode='r:gz') as archive:
        for member in archive:
            name = PurePosixPath(member.name)
            if (not member.isfile() or name.is_absolute() or '..' in name.parts
                    or len(name.parts) != 2 or name.parts[0] != 'openrc-apks'
                    or name.name not in packages or name.name in members):
                raise ValueError('Unexpected OpenRC bundle member')
            data = archive.extractfile(member).read()
            expected = packages[name.name]
            if len(data) != expected['bytes'] or sha(data) != expected['sha256']:
                raise ValueError('OpenRC APK changed in bundle')
            members[name.name] = data
    if set(members) != set(packages):
        raise ValueError('OpenRC package set is incomplete')

    entries, inventory = read_rootfs(BASE_RECEIPT)
    out = ROOT / 'linux-port/artifacts' / ('openrc-bundle-replay-' + str(time.time_ns()))
    runtime = out / 'runtime-root'
    out.mkdir(mode=0o700)
    materialize(entries, runtime)
    cache = runtime / 'var/cache/apk'
    cache.mkdir(mode=0o755, parents=True, exist_ok=True)
    archive_paths = []
    verification = []
    for name, data in sorted(members.items()):
        path = cache / name
        path.write_bytes(data)
        result = subprocess.run([str(APK), '--root', str(runtime), '--keys-dir',
                                 str(runtime / 'etc/apk/keys'), 'verify', str(path)],
                                capture_output=True, text=True)
        if result.returncode or not result.stdout.strip().endswith(': OK'):
            raise ValueError('APK signature verification failed: ' + name)
        verification.append({'name': name, 'output': result.stdout.strip()})
        archive_paths.append(str(path))
    command = [str(APK), '--root', str(runtime), '--arch', 'aarch64', '--keys-dir',
               str(runtime / 'etc/apk/keys'), '--repositories-file', '/dev/null',
               '--cache-dir', str(cache), '--no-network', '--no-scripts', '--cache-packages',
               'add', *archive_paths]
    install = subprocess.run(command, capture_output=True, text=True, timeout=90)
    if install.returncode:
        raise RuntimeError('Offline OpenRC APK install failed: ' + install.stderr[-1500:])
    report = {'state': 'offline-packages-installed', 'started_ns': time.time_ns(),
              'base_rootfs_sha256': inventory['archive_sha256'],
              'bundle_sha256': receipt['bundle_sha256'], 'apk_sha256': APK_SHA256,
              'package_signatures': verification, 'install_stdout': install.stdout,
              'install_stderr': install.stderr, 'runtime_root': str(runtime),
              'network_used': False, 'phone_contacted': False,
              'phone_boot_or_partition_changed': False}
    (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    test = subprocess.run(['python3', str(ROOT / 'tools/test_openrc_userspace_vm.py'),
                           '--runtime-root', str(runtime)], capture_output=True,
                          text=True, timeout=90)
    if test.returncode:
        report['state'] = 'failed'
        report['vm_stdout'], report['vm_stderr'] = test.stdout, test.stderr
        (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
        raise RuntimeError('Offline-installed OpenRC VM boot failed')
    vm_result = json.loads(test.stdout.strip().splitlines()[-1])
    report['state'] = 'offline-openrc-replay-verified'
    report['vm_receipt'] = vm_result['result']
    report['finished_ns'] = time.time_ns()
    (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'state': report['state'], 'result': str(out / 'result.json'),
                      'vm_receipt': report['vm_receipt']}))


if __name__ == '__main__':
    main()
