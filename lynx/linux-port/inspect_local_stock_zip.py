"""Verify a supplied stock ZIP and extract bounded reference files, never flash."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import zipfile

BASE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('archive', type=Path)
    parser.add_argument('--output-name', default='stock-cph2493-August-service')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9_-]+', args.output_name):
        raise ValueError('Output must be a simple artifact directory name')
    source = args.archive.resolve(strict=True)
    output = BASE / 'artifacts' / args.output_name
    if output.exists():
        raise ValueError('Output already exists; choose a fresh name to preserve prior evidence')
    archive_hash = hashlib.sha256()
    with source.open('rb') as stream:
        while chunk := stream.read(8 * 1024 * 1024):
            archive_hash.update(chunk)
    print('Archive SHA-256:', archive_hash.hexdigest(), flush=True)
    limits = {'boot.img': 67108864, 'vendor_boot.img': 67108864, 'dtbo.img': 8388608,
              'vbmeta.img': 8388608, 'vbmeta_system.img': 8388608, 'vbmeta_vendor.img': 8388608,
              'lk.img': 5242880, 'version_info.txt': 1048576, 'DA_BR.bin': 8388608,
              'auth_sv5.auth': 1048576}
    selected = {}
    with zipfile.ZipFile(source) as archive:
        members = archive.infolist()
        if len(members) > 10000 or sum(item.file_size for item in members) > 80 * 1024 ** 3:
            raise ValueError('Unexpected archive expansion size')
        for item in members:
            leaf = Path(item.filename).name
            if leaf not in limits:
                continue
            if leaf in selected or item.file_size > limits[leaf] or item.file_size == 0:
                raise ValueError('Duplicate, oversized or empty component: ' + leaf)
            selected[leaf] = item
        required = {'boot.img', 'vendor_boot.img', 'dtbo.img', 'vbmeta.img', 'lk.img', 'version_info.txt'}
        if not required <= selected.keys():
            raise ValueError('Not the expected service-image package; missing ' + str(required - selected.keys()))
        version_data = archive.read(selected['version_info.txt'])
        version = json.loads(version_data)[0]
        if version.get('platform') != 'k6983v1_64' or 'CPH2493' not in version.get('version_name', ''):
            raise ValueError('Package metadata does not identify the expected CPH2493 platform')
        print('Checking CRC of every archive member; no archive tools will be executed.', flush=True)
        bad = archive.testzip()
        if bad is not None:
            raise ValueError('ZIP CRC failure: ' + bad)
        output.mkdir()
        components = []
        for leaf, item in selected.items():
            data = archive.read(item)
            path = output / leaf
            path.write_bytes(data)
            components.append({'file': str(path), 'archive_entry': item.filename,
                               'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
                               'origin': 'Stock package reference, not a phone readback'})
    lk = (output / 'lk.img').read_bytes()
    builds = sorted(set(match.group().decode() for match in
                        re.finditer(rb'[0-9a-f]{7,40}_\d{12}', lk)))
    recorded = (BASE.parent / 'logs/fastboot-all-20261009.txt').read_text()
    installed = re.search(r'version-bootloader:\s*(\S+)', recorded).group(1)
    report = {'archive_source': str(source), 'archive_bytes': source.stat().st_size,
              'archive_sha256': archive_hash.hexdigest(), 'all_zip_member_crcs_passed': True,
              'model': 'CPH2493', 'platform': version['platform'], 'stock_version': version['version_name'],
              'compile_time': version.get('compile_time'), 'components': components,
              'lk_build_strings': builds, 'installed_bootloader': installed,
              'reference_lk_build_string_matches_installed': any(installed.endswith(build) for build in builds),
              'publisher_authenticity_verified': False, 'avb_verified': False,
              'phone_contacted': False, 'restoration_boot_tested': False,
              'restoration_path_verified': False, 'flash_eligible': False,
              'limits': ['ZIP CRC and self-computed SHA-256 do not independently authenticate the publisher.',
                         'A matching LK build string does not prove all installed partitions match the package.',
                         'AVB signatures, DTB and module ABI require subsequent inspection.',
                         'No packaged executable was run and no phone command was sent.']}
    (output / 'package-inspection.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
