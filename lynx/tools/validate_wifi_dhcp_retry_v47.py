"""Independently validate the offline V47 DHCP retry candidate and rollback."""

import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parent.parent
PORT = ROOT / 'linux-port'
OUT = PORT / 'artifacts/wifi-dhcp-retry-v47-offline'
PARENT = PORT / 'artifacts/persistent-alpine-v46-offline/nord3-persistent-alpine-v46-untested.img'
V33 = PORT / 'artifacts/persistent-openrc-v33-offline/nord3-persistent-openrc-v33-untested.img'
STOCK = PORT / 'artifacts/stock-cph2493-August-eu-ota'
MODEL = ROOT / 'tools/avb-host/avb-boot-model'
MEMBER = 'etc/lynx/wifi-runtime.sh'
sys.path.insert(0, str(PORT))
from image_formats import read_boot_v4, read_newc
from ramdisk_codec import decompress


def sha(data):
    return hashlib.sha256(data).hexdigest()


def run(command, data=None):
    result = subprocess.run(command, input=data, capture_output=True, timeout=30)
    if result.returncode:
        raise ValueError('Validation command failed: ' + str(command))
    return result.stdout


def main():
    build = json.loads((OUT / 'build-result.json').read_text())
    candidate = (OUT / 'nord3-wifi-dhcp-retry-v47-untested.img').read_bytes()
    parent = PARENT.read_bytes()
    v33 = V33.read_bytes()
    stock = (STOCK / 'boot.img').read_bytes()
    if (build['state'] != 'offline-v47-dhcp-retry-candidate-built' or
            sha(candidate) != build['image_sha256'] or
            sha(parent) != build['parent_v46_sha256'] ==
            '6c487df1c16af1717e045167c165271065e9060c5a02b16b8e1b3ce3eca28f91' or
            sha(v33) != '1d65456979d8a48d31de77c987b8aaf9b5ac11af62c51d00fdaff68ad47e747f'):
        raise ValueError('Candidate, V46 or rollback image hash differs')
    image_boot, v46_boot, stock_boot = map(read_boot_v4, (candidate, parent, stock))
    if (len(candidate) != len(parent) == 67_108_864 or
            image_boot['kernel'] != v46_boot['kernel'] or
            image_boot['kernel'] != stock_boot['kernel'] or
            image_boot['cmdline'] != v46_boot['cmdline']):
        raise ValueError('Image size, stock kernel or command line differs')
    primary = read_newc(decompress(image_boot['ramdisk']))
    old_primary = read_newc(decompress(v46_boot['ramdisk']))
    changed = {name for name in set(primary) | set(old_primary)
               if primary.get(name) != old_primary.get(name)}
    if changed != {'etc/lynx/payload-bytes', 'etc/lynx/payload-sha256'}:
        raise ValueError('Unexpected primary member change')
    if sha(primary['init']['data']) != build['init_sha256']:
        raise ValueError('V46 init differs')
    run(['busybox', 'sh', '-n'], primary['init']['data'])
    recipe = json.loads((PORT / 'known-good-v19/recipe.json').read_text())
    offset = recipe['payload_offset']
    old_size = int(old_primary['etc/lynx/payload-bytes']['data'].strip())
    size = int(primary['etc/lynx/payload-bytes']['data'].strip())
    old_payload = parent[offset:offset + old_size]
    payload = candidate[offset:offset + size]
    if (sha(old_payload) != old_primary['etc/lynx/payload-sha256']['data'].strip().decode() or
            sha(payload) != primary['etc/lynx/payload-sha256']['data'].strip().decode() or
            sha(payload) != build['new_payload_sha256']):
        raise ValueError('Supplement checksum differs')
    before = read_newc(gzip.decompress(old_payload))
    after = read_newc(gzip.decompress(payload))
    supplement_changed = {name for name in set(before) | set(after)
                          if before.get(name) != after.get(name)}
    if supplement_changed != {MEMBER}:
        raise ValueError('Unexpected supplement member change')
    old_script, new_script = before[MEMBER]['data'], after[MEMBER]['data']
    if (sha(old_script) != build['old_wifi_sha256'] or
            sha(new_script) != build['new_wifi_sha256'] or
            old_script.count(b'udhcpc -f -n -q -t 6 -T 4') != 1 or
            new_script.count(b'udhcpc -f -n -q -t 6 -T 4') != 1 or
            b'for dhcp_attempt in 1 2 3; do' not in new_script or
            b'[ "$dhcp_bound" = 1 ] || return 144' not in new_script):
        raise ValueError('DHCP retry delta differs')
    run(['busybox', 'sh', '-n'], new_script)
    end = offset + max(old_size, size)
    if candidate[end:] != parent[end:]:
        raise ValueError('Image tail, including AVB footer, differs')
    reference = json.loads((PORT / 'docs/avb-boot-model-results.json').read_text())
    if sha(MODEL.read_bytes()) != reference['binary_sha256']:
        raise ValueError('AVB model differs')
    avb = [json.loads(run([str(MODEL), str(STOCK), str(OUT / 'nord3-wifi-dhcp-retry-v47-untested.img'),
                           '0', str(unlocked)])) for unlocked in (1, 0)]
    if (not avb[0]['slot_data_returned'] or avb[0]['boot_partitions_loaded'] != 1 or
            avb[1]['slot_data_returned'] or avb[1]['boot_partitions_loaded'] != 0):
        raise ValueError('AVB boot model behavior differs')
    result = {'state': 'offline-v47-validation-passed',
              'created_ns': time.time_ns(), 'image_sha256': sha(candidate),
              'parent_v46_sha256': sha(parent), 'rollback_v33_sha256': sha(v33),
              'primary_changes': sorted(changed),
              'supplement_changes': sorted(supplement_changed),
              'avb_cases': avb, 'phone_contacted': False,
              'flash_performed': False,
              'limit': 'Offline validation cannot prove retry success, temperature behavior, or autonomous boot.'}
    (OUT / 'validation.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'state': result['state'], 'result': str(OUT / 'validation.json')}))


if __name__ == '__main__':
    main()
