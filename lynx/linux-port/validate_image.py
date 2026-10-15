"""Validate Lynx's candidate independently of its writer, without device access."""
import argparse
import importlib.util
import hashlib
import json
from pathlib import Path
import stat
from image_formats import module_metadata, read_boot_v4, read_newc, require, static_aarch64
from ramdisk_codec import decompress

base = Path(__file__).resolve().parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--directory', default='artifacts/busybox-offline')
parser.add_argument('--stock-boot', type=Path, default=base / 'artifacts/stock-cph2493-A10/boot.img')
parser.add_argument('--vendor-ramdisk', type=Path, help='Resolve required module files from an exact hash-pinned stock vendor archive')
args = parser.parse_args()
directory = (base / args.directory).resolve()
require(directory.is_relative_to(base / 'artifacts'), 'Artifact directory must remain in workspace')
report = json.loads((directory / 'build-validation.json').read_text())
image = (directory / 'nord3-busybox-candidate.img').read_bytes()
require(hashlib.sha256(image).hexdigest() == report['candidate_sha256'], 'Candidate hash mismatch')
require(len(image) <= 67108864, 'Image exceeds observed download limit')
boot = read_boot_v4(image)
stock = read_boot_v4(args.stock_boot.read_bytes())
require(boot['kernel'] == stock['kernel'], 'Candidate kernel differs from stock')
require(boot['signature_size'] == 0, 'Candidate contains a stale GKI signature')
require(hashlib.sha256(boot['ramdisk']).hexdigest() == report['initramfs_sha256'], 'Ramdisk hash mismatch')
entries = read_newc(decompress(boot['ramdisk']))
resolved = entries
if report.get('vendor_ramdisk_required_for_module_resolution'):
    require(args.vendor_ramdisk is not None, 'This image requires its matching stock vendor ramdisk')
    vendor_bytes = args.vendor_ramdisk.read_bytes()
    require(hashlib.sha256(vendor_bytes).hexdigest() == report['required_vendor_ramdisk_sha256'], 'Wrong vendor ramdisk')
    resolved = {**read_newc(decompress(vendor_bytes)), **entries}
if report.get('avb_footer_present'):
    require(len(image) == 67108864, 'AVB footer must end at the boot partition boundary')
    spec = importlib.util.spec_from_file_location('avbtool', base / 'sources/aosp-avb/avbtool.py')
    avb = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(avb)
    footer = avb.AvbFooter(image[-64:])
    require(footer.version_major == 1, 'Unsupported AVB footer version')
    require(footer.original_image_size == report['avb_original_image_size'], 'AVB original size mismatch')
    require(footer.original_image_size <= footer.vbmeta_offset and
            footer.vbmeta_offset + footer.vbmeta_size <= len(image) - 64,
            'AVB metadata overlaps boot data or exceeds partition')
    _, header, descriptors, _ = avb.Avb()._parse_image(avb.ImageHandler(str(directory / 'nord3-busybox-candidate.img'), read_only=True))
    require(header.flags == 0 and header.rollback_index == 0, 'Unexpected AVB flags or rollback index')
    hashes = [d for d in descriptors if isinstance(d, avb.AvbHashDescriptor)]
    require(len(hashes) == 1 and hashes[0].partition_name == 'boot', 'Missing unique boot hash descriptor')
    descriptor = hashes[0]
    require(descriptor.image_size == footer.original_image_size and descriptor.hash_algorithm == 'sha256', 'Wrong AVB boot hash coverage')
    hash_matches = hashlib.sha256(descriptor.salt + image[:descriptor.image_size]).digest() == descriptor.digest
    if report.get('diagnostic_metadata_mode') == 'preserved-stock-metadata-with-payload-hash-mismatch':
        stock_image = args.stock_boot.read_bytes()
        stock_footer = avb.AvbFooter(stock_image[-64:])
        stock_blob = stock_image[stock_footer.vbmeta_offset:stock_footer.vbmeta_offset + stock_footer.vbmeta_size]
        blob = image[footer.vbmeta_offset:footer.vbmeta_offset + footer.vbmeta_size]
        require(image[-64:] == stock_image[-64:] and blob == stock_blob, 'Stock metadata or footer was modified')
        require(hashlib.sha256(blob).hexdigest() == report['preserved_stock_metadata_sha256'], 'Metadata SHA mismatch')
        require(header.algorithm_type == 1 and avb.verify_vbmeta_signature(header, blob), 'Stock RSA metadata signature invalid')
        require(not hash_matches and report['avb_hash_matches_modified_payload'] is False,
                'Expected unlocked-policy diagnostic hash mismatch absent')
    else:
        require(header.algorithm_type == 0, 'Unexpected AVB algorithm')
        require(hash_matches, 'AVB boot digest does not match payload')
init_source = (base / report.get('native_init_source', 'init')).resolve()
require(init_source.is_relative_to(base) and init_source.is_file(), 'Init source must stay in the project')
require(entries['init']['data'] == init_source.read_bytes(), 'Packaged init differs from source')
require(entries['init']['mode'] == stat.S_IFREG | 0o755, 'Init is not executable')
require(stat.S_ISLNK(entries['bin/sh']['mode']), 'Shell is not a symlink')
require(entries['bin/sh']['data'] == b'busybox', 'Wrong shell target')
static_aarch64(entries['bin/busybox']['data'])
console = entries['dev/console']
require(stat.S_ISCHR(console['mode']) and (console['rdevmajor'], console['rdevminor']) == (5, 1), 'Wrong initial console node')
order = entries['etc/usb-modules.load']['data'].decode().splitlines()
require(order == report['usb_module_load_order'], 'Module load order differs from build report')
for name in order:
    metadata = module_metadata(resolved['lib/modules/' + name]['data'])
    require(metadata['values']['vermagic'][0].split()[0] == report['stock_kernel_release'], 'Module/kernel release mismatch')
    require(metadata['has_symbol_versions'], 'Module lacks symbol versions')
require(report['flash_eligible'] is False, 'Unverified candidate incorrectly marked flash eligible')
print(f'Validated Lynx candidate: {len(image):,} bytes, {len(entries)} entries, {len(order)} matching modules; flashing remains blocked.')
