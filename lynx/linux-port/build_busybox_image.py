"""Reproducible offline BusyBox build; never operate on a phone."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import stat
import struct
import subprocess
from image_formats import module_metadata, read_boot_v4, read_newc, require, static_aarch64

base = Path(__file__).resolve().parent
stock = base / 'artifacts/stock-cph2493-A10'
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--validate-on-argus', action='store_true', help='Refresh the ARM64 applet/syntax evidence on Argus; no init execution')
parser.add_argument('--output', default='artifacts/busybox-offline', help='Output directory within this project artifacts directory')
parser.add_argument('--stock-dir', type=Path, default=stock)
parser.add_argument('--stock-manifest', type=Path, default=base / 'docs/stock-component-manifest.json')
parser.add_argument('--vendor-audit', type=Path, default=base / 'docs/vendor-ramdisk-audit.json')
args = parser.parse_args()
stock = args.stock_dir
output = (base / args.output).resolve()
require(output.is_relative_to(base / 'artifacts'), 'Build output must remain within project artifacts')
output.mkdir(exist_ok=True)
busybox = (base / 'artifacts/busybox-aarch64-static').read_bytes()
init = (base / 'init').read_bytes()
static_aarch64(busybox)
provenance = json.loads((base / 'docs/busybox-provenance.json').read_text())
require(hashlib.sha256(busybox).hexdigest() == provenance['binary_sha256'], 'BusyBox differs from its validated package')
stock_manifest = json.loads(args.stock_manifest.read_text())
stock_hashes = {Path(item['file']).name: item['sha256'] for item in stock_manifest['components']}
for name in ('boot.img', 'vendor_boot.img'):
    require(hashlib.sha256((stock / name).read_bytes()).hexdigest() == stock_hashes[name], 'Stock component changed: ' + name)
ramdisk_audit = json.loads(args.vendor_audit.read_text())
require(ramdisk_audit['stock_vendor_boot_sha256'] == stock_hashes['vendor_boot.img'], 'Module provenance differs from stock vendor boot')
module_hashes = {Path(item['path']).name: item['sha256'] for item in ramdisk_audit['entries'] if item['path'].endswith('.ko')}
kernel_release = ramdisk_audit['kernel_banners'][0].split()[2]
subprocess.run(['bash', '-n', str(base / 'init')], check=True)

# Remote validation is opt-in; subsequent builds use hash-bound cached evidence.
proof_path = base / 'docs/arm64-userspace-validation.json'
ssh = ['ssh', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes', '-o', 'ConnectTimeout=8', 'argus']
remote_dir = '/noobia/lynx/linux-port/validation'
if args.validate_on_argus:
    subprocess.run(ssh + ['mkdir -p ' + remote_dir], check=True)
    subprocess.run(['scp', '-q', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes', str(base / 'artifacts/busybox-aarch64-static'), str(base / 'init'), 'argus:' + remote_dir + '/'], check=True)
    result = subprocess.run(ssh + [remote_dir + '/busybox-aarch64-static --list-full'], check=True, capture_output=True, text=True)
    setsid_help = subprocess.run(ssh + [remote_dir + '/busybox-aarch64-static setsid --help'], capture_output=True, text=True)
    require('-c' in setsid_help.stdout + setsid_help.stderr, 'BusyBox setsid must support a controlling terminal')
    subprocess.run(ssh + [remote_dir + '/busybox-aarch64-static sh -n ' + remote_dir + '/init'], check=True)
    proof = {'host': 'argus', 'busybox_sha256': hashlib.sha256(busybox).hexdigest(), 'init_sha256': hashlib.sha256(init).hexdigest(), 'applets': result.stdout.splitlines(), 'setsid_help': setsid_help.stdout + setsid_help.stderr, 'syntax_validated_without_running_init': True}
    proof_path.write_text(json.dumps(proof, indent=2) + '\n')
require(proof_path.is_file(), 'ARM64 evidence missing; run once with --validate-on-argus')
proof = json.loads(proof_path.read_text())
require(proof['busybox_sha256'] == hashlib.sha256(busybox).hexdigest(), 'ARM64 evidence does not match BusyBox')
require(proof['init_sha256'] == hashlib.sha256(init).hexdigest(), 'ARM64 evidence does not match init; refresh with --validate-on-argus')
applets = {Path(line).name for line in proof['applets']}
required = {'sh', 'mount', 'mknod', 'mdev', 'insmod', 'setsid', 'sleep', 'cat', 'ip', 'mkdir', 'ln', 'grep', 'uname'}
require(required <= applets, 'Missing BusyBox applets: ' + str(required - applets))
(output / 'setsid-help.txt').write_text(proof['setsid_help'])
(output / 'busybox-applets.txt').write_text('\n'.join(proof['applets']) + '\n')

module_root = stock / 'vendor-ramdisk-unpacked/lib/modules'
dependencies = {}
for line in (module_root / 'modules.dep').read_text().splitlines():
    module, deps = line.split(':', 1)
    dependencies[Path(module).name] = [Path(p).name for p in deps.split()]
seeds = ['oplus_project.ko', 'pinctrl-mt6983.ko', 'clk-mt6983.ko', 'mtk-pmic-wrap.ko', 'mtk-spmi-pmic.ko', 'spmi-mtk-pmif.ko', 'mt6363-regulator.ko', 'mt6373-regulator.ko', 'mt6315-regulator.ko', 'mtk-scpsys-mt6983.ko', 'phy-mtk-xsphy.ko', 'tcpc_mt6375.ko', 'extcon-mtk-usb.ko', 'mtu3.ko']
ordered = []
visiting = set()
seen = set()


def add_module(name):
    if name in seen:
        return
    assert name not in visiting, 'Module dependency cycle: ' + name
    assert (module_root / name).is_file(), 'Missing module: ' + name
    payload = (module_root / name).read_bytes()
    require(hashlib.sha256(payload).hexdigest() == module_hashes[name], 'Stock module changed: ' + name)
    metadata = module_metadata(payload)
    require(metadata['values']['vermagic'][0].split()[0] == kernel_release, 'Kernel/module version mismatch: ' + name)
    require(metadata['has_symbol_versions'], 'Module lacks the stock symbol-version contract: ' + name)
    visiting.add(name)
    for dependency in dependencies.get(name, []):
        add_module(dependency)
    visiting.remove(name)
    seen.add(name)
    ordered.append(name)


for name in seeds:
    add_module(name)
load_order = ('\n'.join(ordered) + '\n').encode()
(output / 'usb-modules.load').write_bytes(load_order)

archive = bytearray()
inode = 1
inventory = []


def add(name, mode, payload=b'', major=0, minor=0):
    global inode
    encoded = name.encode() + b'\0'
    values = [inode, mode, 0, 0, 1, 0, len(payload), 0, 0, major, minor, len(encoded), 0]
    header = b'070701' + ''.join(f'{value:08x}' for value in values).encode()
    archive.extend(header + encoded)
    archive.extend(b'\0' * (-len(archive) % 4))
    archive.extend(payload)
    archive.extend(b'\0' * (-len(archive) % 4))
    inventory.append({'path': name, 'mode': oct(mode), 'size': len(payload), 'sha256': hashlib.sha256(payload).hexdigest()})
    inode += 1


for name in ('bin', 'sbin', 'dev', 'proc', 'sys', 'sys/kernel', 'sys/kernel/config', 'run', 'tmp', 'etc', 'lib', 'lib/modules'):
    add(name, stat.S_IFDIR | (0o1777 if name == 'tmp' else 0o755))
add('dev/console', stat.S_IFCHR | 0o600, major=5, minor=1)
add('dev/null', stat.S_IFCHR | 0o666, major=1, minor=3)
add('bin/busybox', stat.S_IFREG | 0o755, busybox)
add('bin/sh', stat.S_IFLNK | 0o777, b'busybox')
for applet in sorted(applets - {'busybox', 'sh'}):
    add('bin/' + applet, stat.S_IFLNK | 0o777, b'busybox')
add('init', stat.S_IFREG | 0o755, init)
add('etc/usb-modules.load', stat.S_IFREG | 0o644, load_order)
for name in ordered:
    add('lib/modules/' + name, stat.S_IFREG | 0o644, (module_root / name).read_bytes())
add('TRAILER!!!', 0)
archive.extend(b'\0' * (-len(archive) % 512))
ramdisk = gzip.compress(bytes(archive), compresslevel=9, mtime=0)
parsed_archive = read_newc(bytes(archive))
require(parsed_archive['dev/console']['rdevmajor'] == 5 and parsed_archive['dev/console']['rdevminor'] == 1, 'Wrong initial console device')
require(parsed_archive['init']['data'] == init, 'Initramfs init changed during packaging')
(output / 'initramfs.cpio.gz').write_bytes(ramdisk)
(output / 'initramfs-inventory.json').write_text(json.dumps(inventory, indent=2) + '\n')

original = (stock / 'boot.img').read_bytes()
stock_parts = read_boot_v4(original)
assert original[:8] == b'ANDROID!' and struct.unpack_from('<I', original, 40)[0] == 4
kernel_size = struct.unpack_from('<I', original, 8)[0]
kernel = original[4096:4096 + kernel_size]
header = bytearray(original[:1584])
struct.pack_into('<I', header, 12, len(ramdisk))
struct.pack_into('<I', header, 1580, 0)  # The old GKI signature does not describe this modified image.
cmdline = b'rdinit=/init panic=10 noobia.usb=1'
header[44:1580] = cmdline.ljust(1536, b'\0')
align = lambda value: (value + 4095) // 4096 * 4096
candidate = bytes(header).ljust(4096, b'\0') + kernel.ljust(align(len(kernel)), b'\0') + ramdisk.ljust(align(len(ramdisk)), b'\0')
assert len(candidate) <= 67108864, 'Candidate exceeds boot partition/fastboot download size'
parsed_candidate = read_boot_v4(candidate)
require(parsed_candidate['kernel'] == stock_parts['kernel'], 'Kernel changed during repacking')
require(parsed_candidate['ramdisk'] == ramdisk, 'Ramdisk changed during repacking')
image_path = output / 'nord3-busybox-candidate.img'
image_path.write_bytes(candidate)

report = {'status': 'offline-validated candidate; NOT hardware-tested or approved for flashing', 'device': 'OnePlus Nord 3 CPH2493 / k6983v1_64', 'header_version': 4, 'image_bytes': len(candidate), 'download_limit_bytes': 67108864, 'ramdisk_bytes': len(ramdisk), 'kernel_identical_to_stock': candidate[4096:4096 + kernel_size] == kernel, 'kernel_sha256': hashlib.sha256(kernel).hexdigest(), 'candidate_sha256': hashlib.sha256(candidate).hexdigest(), 'initramfs_sha256': hashlib.sha256(ramdisk).hexdigest(), 'busybox_executed_on_arm64_argus': True, 'init_syntax_checked_by_target_busybox': True, 'usb_module_count': len(ordered), 'usb_module_load_order': ordered, 'module_hashes_and_vermagic_verified': True, 'stock_kernel_release': kernel_release, 'flash_operations_performed': 0, 'hardware_boot_test_performed': False, 'flash_eligible': False, 'limitations': ['Current installed vendor_boot DTB/DTBO has not been read back or compared.', 'Bootloader RAM boot and fetch commands are unsupported in observed trials.', 'Installed firmware build has not been matched to stock package.', 'A custom generic init may affect the Android recovery entry; preservation is not validated.', 'No display bring-up or SSH server yet.', 'Manufacturer signatures are not valid for the modified candidate.']}
(output / 'build-validation.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({k: v for k, v in report.items() if k != 'usb_module_load_order'}, indent=2))
