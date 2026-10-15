"""List phone firmware ZIP contents inside the NVMe tar without extracting."""
import json
from pathlib import Path
import tarfile
import zipfile

archive_path = Path('/noobia/backups/argus-recovery-20260819/mnt-nvme.tar')
member_name = 'nvme/images/OnePlus_Nord_3_5G_CPH2493_MT6983_GDPR_11_A.10_230707_MXML.zip'
output = Path('/noobia/lynx/logs/nord3-firmware-inventory.json')
destination = Path('/noobia/lynx/linux-port/artifacts/stock-cph2493-A10')
destination.mkdir(parents=True, exist_ok=True)
with tarfile.open(archive_path, 'r:') as archive:
    with archive.extractfile(member_name) as handle:
        with zipfile.ZipFile(handle) as firmware:
            entries = [{'name': i.filename, 'size': i.file_size, 'compressed_size': i.compress_size, 'crc32': f'{i.CRC:08x}'} for i in firmware.infolist()]
            output.write_text(json.dumps(entries, indent=2) + '\n')
            print('Firmware ZIP entries:', len(entries))
            selected = ('Firmware/IMAGES/boot.img', 'Firmware/IMAGES/vendor_boot.img', 'Firmware/IMAGES/dtbo.img', 'Firmware/IMAGES/vbmeta.img', 'Firmware/IMAGES/vbmeta_system.img', 'Firmware/IMAGES/vbmeta_vendor.img', 'Firmware/build.prop', 'Firmware/version_info.txt', 'Firmware/all_files_hash_checksum.txt', 'Firmware/IMAGES/MT6983_21871_Android_scatter.txt', 'Firmware/META/super_def.10100111.json')
            for info in firmware.infolist():
                if any(info.filename.endswith('/' + name) for name in selected):
                    target = destination / Path(info.filename).name
                    data = firmware.read(info)
                    if target.exists() and target.read_bytes() != data:
                        raise RuntimeError('Existing extracted artifact differs: ' + str(target))
                    target.write_bytes(data)
                    print('Extracted', target.name, len(data), 'bytes (ZIP CRC verified)')
