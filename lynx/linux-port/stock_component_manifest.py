"""Describe stock components; distinguish them from on-device backups."""
import hashlib
import json
from pathlib import Path

base = Path(__file__).resolve().parent
stock = base / 'artifacts/stock-cph2493-A10'
version = json.loads((stock / 'version_info.txt').read_text())[0]
components = []
for name, partitions in [('boot.img', ['boot_a', 'boot_b']), ('vendor_boot.img', ['vendor_boot_a', 'vendor_boot_b']), ('dtbo.img', ['dtbo_a', 'dtbo_b']), ('vbmeta.img', ['vbmeta_a', 'vbmeta_b']), ('vbmeta_system.img', ['vbmeta_system_a', 'vbmeta_system_b']), ('vbmeta_vendor.img', ['vbmeta_vendor_a', 'vbmeta_vendor_b'])]:
    path = stock / name
    data = path.read_bytes()
    components.append({'file': str(path), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(), 'corresponding_partition_names': partitions, 'origin': 'Archived stock firmware ZIP; NOT read from phone'})
report = {'model': 'CPH2493', 'platform': version['platform'], 'stock_version': version['version_name'], 'compile_time': version['compile_time'], 'archive_source': '/noobia/backups/argus-recovery-20260819/mnt-nvme.tar', 'archive_verified_sha256': 'd327a7a7c77d169325fb43287598c79b2743337354bf4f8355d54c90021ae2b7', 'model_matches_user_identification': True, 'installed_phone_firmware_version_matched': False, 'on_device_partition_backup_obtained': False, 'components': components, 'flash_operations_performed': 0}
(base / 'docs/stock-component-manifest.json').write_text(json.dumps(report, indent=2) + '\n')
print('Stock package:', report['stock_version'])
for item in components:
    print(Path(item['file']).name, item['bytes'], item['sha256'])
print('These are package images, not backups of the currently installed partitions.')
