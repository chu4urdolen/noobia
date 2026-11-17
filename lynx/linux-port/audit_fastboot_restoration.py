"""Assess saved bootloader and restoration images offline; never invoke Fastboot."""
import hashlib
import json
from pathlib import Path
import re

BASE = Path(__file__).resolve().parent
PHONE = BASE.parent
service = json.loads((BASE / 'docs/service-resource-audit.json').read_text())
reference = next(item for item in service['resources'] if item['name'] == 'lk.img')
data = (BASE / 'artifacts/service-reference/lk.img').read_bytes()
if hashlib.sha256(data).hexdigest() != reference['sha256']:
    raise ValueError('Stock bootloader reference changed')
strings = [(match.start(), match.group().decode())
           for match in re.finditer(rb'[ -~]{4,}', data)]
versions = [{'offset': offset, 'value': value} for offset, value in strings
            if re.fullmatch(r'[0-9a-f]{7,40}_\d{12}', value)]
log = (PHONE / 'logs/fastboot-all-20261009.txt').read_text()
installed = re.search(r'version-bootloader:\s*(\S+)', log).group(1)
selected = [{'offset': offset, 'value': value} for offset, value in strings
            if value in ('flash', 'flash:', 'Tflash:', 'getvar:', 'reboot-bootloader',
                         'reboot-recovery', 'vendor_boot', 'k6983v1_64')
            or 'rollback index is less than' in value
            or 'img is rollbacked' in value
            or 'fastboot mode idle for a while' in value]
images = []
expected = {'boot': ('49cd8f7e319ade8e78f54fd275a56a4110bab37a7917f715860a25f6b4442232', 67108864),
            'vendor_boot': ('c644298d48b82c0ab94f80b0fb10042fbca67b9a4b42553e758ab8e8b3036174', 67108864),
            'dtbo': ('5bd6863b646abe50918c491b18506f39d91c1d3eccc548c0139ac6766b3eb836', 8388608),
            'vbmeta': ('f8047a62e871bbf6d5922f41e29800ee9e9548dbf8c75bad24be9647f4102d03', 8388608)}
for name, (digest, partition_bytes) in expected.items():
    path = BASE / 'artifacts/stock-cph2493-A10' / (name + '.img')
    payload = path.read_bytes()
    actual = hashlib.sha256(payload).hexdigest()
    if actual != digest or len(payload) > partition_bytes:
        raise ValueError(f'Invalid saved restoration image: {name}')
    images.append({'partition': name + '_a', 'file': str(path), 'bytes': len(payload),
                   'partition_bytes': partition_bytes, 'sha256': actual,
                   'hash_and_size_verified': True, 'on_device_backup': False})
report = {'installed_bootloader_from_saved_getvar': installed,
          'reference_lk_sha256': reference['sha256'], 'reference_build_strings': versions,
          'reference_matches_installed_bootloader': any(installed.endswith(v['value']) for v in versions),
          'reference_string_evidence': selected, 'restoration_images': images,
          'physical_fastboot_return_observed': True,
          'boot_partition_write_support_tested': False,
          'restoration_boot_tested': False, 'phone_contacted': False,
          'flash_eligible': False,
          'limits': ['Binary strings are static clues, not executed code or proof of policy.',
                     'Reference LK is July 2023; observed installed LK is August 2023.',
                     'Image integrity and size do not prove installed DTB compatibility or rollback acceptance.',
                     'Do not flash lk, preloader or slot B to make the package match.']}
(BASE / 'docs/fastboot-restoration-audit.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
