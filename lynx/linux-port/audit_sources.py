"""Offline boot-image and pinned source inspection; no device commands."""
import gzip
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys

base = Path(__file__).resolve().parent
artifacts = base / 'artifacts/stock-cph2493-A10'
snapshots = base / 'sources/snapshots'
snapshots.mkdir(exist_ok=True)
report = {'sources': {}, 'stock': {}}


def git(repo, *args):
    return subprocess.run(['git', '-C', str(repo), *args], check=True, capture_output=True).stdout


for name in (() if '--stock-only' in sys.argv else ('kernel-mt6983', 'modules-mt6983', 'device-oneplus-vitamin', 'vendor-vitamin', 'pmaports')):
    repo = base / 'sources' / name
    if not (repo / '.git').exists():
        continue
    try:
        commit = git(repo, 'rev-parse', 'HEAD').decode().strip()
    except subprocess.CalledProcessError:
        print(name, 'clone not yet complete', flush=True)
        continue
    paths = git(repo, 'ls-tree', '-r', '--name-only', 'HEAD').decode().splitlines()
    (snapshots / (name + '.paths')).write_text('\n'.join(paths) + '\n')
    report['sources'][name] = {'commit': commit, 'files': len(paths)}
    print(name, commit, len(paths), 'paths', flush=True)
    if name == 'kernel-mt6983':
        selected = [p for p in paths if p.startswith('arch/arm64/configs/') and ('gki' in p or '6983' in p or '21871' in p)]
        selected += [p for p in paths if p.startswith('arch/arm64/boot/dts/') and ('6983' in p or '21871' in p)]
        selected += [p for p in ('Makefile', 'build.config.mtk.aarch64', 'build.config.gki.aarch64', 'drivers/usb/mtu3/Kconfig', 'drivers/usb/mtu3/Makefile') if p in paths]
    elif name == 'modules-mt6983':
        selected = [p for p in paths if p.endswith(('build.config', 'README.md')) and ('mediatek' in p or 'oplus' in p)]
    elif name == 'pmaports':
        selected = [p for p in paths if ('oneplus' in p and p.endswith(('deviceinfo', 'APKBUILD'))) or ('mt6983' in p or 'vitamin' in p)]
        report['sources'][name]['nord3_paths'] = [p for p in paths if 'vitamin' in p or 'mt6983' in p]
    else:
        selected = []
    report['sources'][name]['selected'] = selected
    for p in selected:
        target = snapshots / name / p
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(git(repo, 'show', 'HEAD:' + p))
    print('Saved', len(selected), 'source excerpts for', name, flush=True)

boot = (artifacts / 'boot.img').read_bytes()
assert boot[:8] == b'ANDROID!'
version = struct.unpack_from('<I', boot, 40)[0]
assert version in (3, 4)
kernel_size, ramdisk_size, os_version, header_size = struct.unpack_from('<4I', boot, 8)
kernel = boot[4096:4096 + kernel_size]
report['stock']['boot'] = {'header_version': version, 'header_size': header_size, 'kernel_size': kernel_size, 'ramdisk_size': ramdisk_size, 'sha256': hashlib.sha256(boot).hexdigest(), 'cmdline': boot[44:1580].split(b'\0', 1)[0].decode(errors='replace')}
(artifacts / 'Image.gz').write_bytes(kernel)
if kernel[:2] == b'\x1f\x8b':
    image = gzip.decompress(kernel)
else:
    image = kernel
(artifacts / 'Image').write_bytes(image)
start = image.find(b'IKCFG_ST')
end = image.find(b'IKCFG_ED', start + 8)
if start >= 0 and end > start:
    config = gzip.decompress(image[start + 8:end]).decode()
    (artifacts / 'stock-kernel.config').write_text(config)
    report['stock']['config_available'] = True
    report['stock']['usb_config'] = [line for line in config.splitlines() if any(key in line for key in ('CONFIG_USB_', 'CONFIG_USB_CONFIGFS', 'CONFIG_NET', 'CONFIG_DEVTMPFS', 'CONFIG_BLK_DEV_INITRD', 'CONFIG_MODULE_SIG', 'CONFIG_MODVERSIONS'))]
else:
    report['stock']['config_available'] = False
banner_start = image.find(b'Linux version ')
if banner_start >= 0:
    report['stock']['kernel_banner'] = image[banner_start:banner_start + 400].split(b'\0', 1)[0].decode(errors='replace')

vendor = (artifacts / 'vendor_boot.img').read_bytes()
assert vendor[:8] == b'VNDRBOOT'
vendor_version, page_size = struct.unpack_from('<2I', vendor, 8)
vendor_ramdisk_size = struct.unpack_from('<I', vendor, 24)[0]
vendor_header_size, dtb_size = struct.unpack_from('<2I', vendor, 2096)
align = lambda value: (value + page_size - 1) // page_size * page_size
ramdisk_offset = align(vendor_header_size)
dtb_offset = ramdisk_offset + align(vendor_ramdisk_size)
(artifacts / 'vendor-ramdisk.bin').write_bytes(vendor[ramdisk_offset:ramdisk_offset + vendor_ramdisk_size])
(artifacts / 'stock.dtb').write_bytes(vendor[dtb_offset:dtb_offset + dtb_size])
report['stock']['vendor_boot'] = {'header_version': vendor_version, 'page_size': page_size, 'ramdisk_size': vendor_ramdisk_size, 'dtb_size': dtb_size, 'sha256': hashlib.sha256(vendor).hexdigest(), 'cmdline': vendor[28:2076].split(b'\0', 1)[0].decode(errors='replace')}
if vendor_version == 4:
    table_size, entry_count, entry_size, bootconfig_size = struct.unpack_from('<4I', vendor, 2112)
    table_offset = dtb_offset + align(dtb_size)
    report['stock']['vendor_boot']['ramdisk_fragments'] = []
    for i in range(entry_count):
        pos = table_offset + i * entry_size
        size, offset, kind = struct.unpack_from('<3I', vendor, pos)
        name = vendor[pos + 12:pos + 44].split(b'\0', 1)[0].decode(errors='replace')
        report['stock']['vendor_boot']['ramdisk_fragments'].append({'name': name, 'size': size, 'offset': offset, 'type': kind})
        (artifacts / ('vendor-fragment-' + str(i) + '.bin')).write_bytes(vendor[ramdisk_offset + offset:ramdisk_offset + offset + size])
    bootconfig_offset = table_offset + align(table_size)
    (artifacts / 'stock.bootconfig').write_bytes(vendor[bootconfig_offset:bootconfig_offset + bootconfig_size])

(base / 'docs' / ('stock-boot-audit.json' if '--stock-only' in sys.argv else 'source-and-boot-audit.json')).write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({k: v for k, v in report['stock'].items() if k != 'usb_config'}, indent=2))
