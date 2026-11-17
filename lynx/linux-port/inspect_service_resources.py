"""Extract small diagnostic references from the original archive; never flash them."""
import hashlib
import json
from pathlib import Path
import re
import tarfile
import zipfile

base = Path(__file__).resolve().parent
archive_path = Path('/noobia/backups/argus-recovery-20260819/mnt-nvme.tar')
zip_name = 'OnePlus_Nord_3_5G_CPH2493_MT6983_GDPR_11_A.10_230707_MXML.zip'
output = base / 'artifacts/service-reference'
output.mkdir(exist_ok=True)
report = {'reference_only': True, 'flash_eligible': False, 'resources': []}
with tarfile.open(archive_path, 'r:') as archive:
    members = [m for m in archive if m.name.endswith('/' + zip_name)]
    if len(members) != 1:
        raise ValueError('Expected exactly one firmware ZIP')
    stream = archive.extractfile(members[0])
    with zipfile.ZipFile(stream) as firmware:
        for entry in firmware.infolist():
            leaf = Path(entry.filename).name
            if leaf not in ('DA_BR.bin', 'auth_sv5.auth', 'flash.xml', 'flash.xsd', 'lk.img'):
                continue
            if entry.file_size > 8 * 1024 * 1024:
                raise ValueError('Unexpectedly large service reference')
            data = firmware.read(entry)  # ZIP CRC checked by read.
            (output / leaf).write_bytes(data)
            item = {'name': leaf, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
                    'archive_entry': entry.filename, 'first_32_bytes_hex': data[:32].hex()}
            if leaf == 'lk.img':
                strings = re.findall(rb'[ -~]{8,}', data)
                item['version_strings'] = [s.decode()[:200] for s in strings
                                           if b'k6983v1_64_' in s or b'45ca337' in s]
            report['resources'].append(item)
(base / 'docs/service-resource-audit.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
