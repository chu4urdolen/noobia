"""Validate an existing native sysfs partition capture offline; never reads devices."""
import argparse
import hashlib
import json
import re
import uuid
from pathlib import Path

V19_HASH = '5ce2dbf8a7c132fa7e31f6be70aa76f83afe8c293e2cd5f02251a532486fd851'


def analyze(raw):
    text = raw.decode('utf-8')
    if not text.startswith('LYNX_PARTITION_MAP_BEGIN\n') or not text.endswith('LYNX_PARTITION_MAP_END\n'):
        raise ValueError('Incomplete partition capture')
    boot_id = str(uuid.UUID(text.splitlines()[1]))
    disk_text, remainder = text.split('\nDISK\n', 1)[1].split('\nPARTITION ', 1)
    disk = dict(line.split('=', 1) for line in disk_text.splitlines())
    disk_bytes = int(disk['size']) * 512
    logical = int(disk['queue/logical_block_size'])
    if logical not in (512, 4096) or disk_bytes <= 0 or disk_bytes % logical:
        raise ValueError('Unsupported disk geometry')
    part_text, rest = remainder.split('\nFILESYSTEM_SUPPORT\n', 1)
    filesystems, image_hash = rest.split('\nBOOT_IMAGE_HASH\n', 1)
    image_lines = image_hash.splitlines()
    if image_lines != [V19_HASH + '  /dev/sdc39', 'LYNX_PARTITION_MAP_END']:
        raise ValueError('Installed boot_a differs from the frozen V19 image')
    partitions, labels, numbers = [], set(), set()
    for section in ('PARTITION ' + part_text).split('PARTITION ')[1:]:
        lines = section.strip().splitlines()
        device = lines[0]
        values = dict(line.split('=', 1) for line in lines[1:])
        if not re.fullmatch(r'sdc[1-9][0-9]*', device) or values['DEVNAME'] != device:
            raise ValueError('Unexpected block device')
        number = int(values['PARTN'])
        label = values['PARTNAME']
        if number != int(device[3:]) or number in numbers or label in labels:
            raise ValueError('Duplicate or mismatched partition identity')
        if not re.fullmatch(r'[a-zA-Z0-9_-]+', label):
            raise ValueError('Unexpected partition label')
        if values['dev'] != values['MAJOR'] + ':' + values['MINOR']:
            raise ValueError('Device number mismatch')
        start, size = int(values['start']) * 512, int(values['size']) * 512
        if start <= 0 or size <= 0 or (start + size) > disk_bytes or start % logical or size % logical:
            raise ValueError('Out-of-bounds or unaligned partition')
        partitions.append({'device': device, 'number': number, 'label': label,
                           'device_number': values['dev'], 'start_bytes': start,
                           'size_bytes': size, 'end_bytes_exclusive': start + size})
        labels.add(label)
        numbers.add(number)
    partitions.sort(key=lambda entry: entry['start_bytes'])
    for previous, current in zip(partitions, partitions[1:]):
        if previous['end_bytes_exclusive'] > current['start_bytes']:
            raise ValueError('Overlapping partitions')
    required = {'boot_a', 'boot_b', 'vendor_boot_a', 'vendor_boot_b', 'init_boot_a', 'init_boot_b',
                'dtbo_a', 'dtbo_b', 'vbmeta_a', 'vbmeta_b', 'super', 'userdata'}
    if not required <= labels:
        raise ValueError('Missing boot/recovery/storage partition labels')
    boot_a = next(entry for entry in partitions if entry['label'] == 'boot_a')
    if boot_a['device'] != 'sdc39' or boot_a['size_bytes'] != 64 * 1024 * 1024:
        raise ValueError('Unexpected boot_a geometry')
    return {'passed': True, 'boot_id': boot_id, 'disk': 'sdc', 'disk_bytes': disk_bytes,
            'logical_block_bytes': logical, 'physical_block_bytes': int(disk['queue/physical_block_size']),
            'sysfs_sector_bytes': 512, 'partition_count': len(partitions), 'partitions': partitions,
            'filesystem_support': filesystems.splitlines(), 'installed_boot_a_sha256': V19_HASH,
            'phone_contacted_by_audit': False, 'partition_writes': False,
            'limits': 'Kernel sysfs map and a read-only boot_a hash, not an independent GPT CRC or filesystem integrity check.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--receipt', type=Path, required=True)
    args = parser.parse_args()
    receipt = json.loads(args.receipt.read_text())
    operation = next(item for item in receipt['operations'] if item['name'] == 'command')
    raw = args.receipt.with_name('command.stdout').read_bytes()
    if not receipt.get('native_identity_verified') or operation.get('exit_code') != 0:
        raise ValueError('Successful native identity and command required')
    if hashlib.sha256(raw).hexdigest() != operation['stdout_sha256']:
        raise ValueError('Raw capture hash mismatch')
    report = analyze(raw)
    report.update(capture_receipt=str(args.receipt.resolve()), capture_sha256=hashlib.sha256(raw).hexdigest())
    output = args.receipt.with_name('partition-map-analysis.json')
    output.write_text(json.dumps(report, indent=2) + '\n')
    output.chmod(0o600)
    print(json.dumps({'passed': True, 'partitions': report['partition_count'], 'disk_bytes': report['disk_bytes'],
                      'installed_boot_a_matches_v19': True, 'result': str(output)}))


if __name__ == '__main__':
    main()
