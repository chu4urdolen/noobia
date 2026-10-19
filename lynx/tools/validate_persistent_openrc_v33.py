"""Independently validate V33's PID 1 stdio fix offline."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
PORT = ROOT / 'linux-port'
OUT = PORT / 'artifacts/persistent-openrc-v33-offline'
PARENT = PORT / 'artifacts/persistent-openrc-v32-offline/nord3-persistent-openrc-v32-untested.img'
STOCK_DIR = PORT / 'artifacts/stock-cph2493-August-eu-ota'
STOCK_BOOT = STOCK_DIR / 'boot.img'
MODEL = ROOT / 'tools/avb-host/avb-boot-model'
sys.path.insert(0, str(PORT))
from image_formats import read_boot_v4, read_newc
from ramdisk_codec import decompress
from build_persistent_openrc_v33 import OLD, NEW


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    build = json.loads((OUT / 'build-result.json').read_text())
    image = OUT / 'nord3-persistent-openrc-v33-untested.img'
    data, parent, stock = image.read_bytes(), PARENT.read_bytes(), STOCK_BOOT.read_bytes()
    recipe = json.loads((PORT / 'known-good-v19/recipe.json').read_text())
    offset = recipe['payload_offset']
    if (build['state'] != 'offline-stdio-fix-candidate-built' or
            sha(data) != build['image_sha256'] or
            sha(parent) != build['parent_v32_sha256'] or
            sha(stock) != 'a67f03d7b826b834c23653b67eaa6efa971eb70ef8af19eee4d33fb5fc7fe995' or
            data[offset:] != parent[offset:]):
        raise ValueError('Candidate, V32 parent, stock or supplement differs')
    boot, parent_boot, stock_boot = map(read_boot_v4, (data, parent, stock))
    if boot['kernel'] != parent_boot['kernel'] or boot['kernel'] != stock_boot['kernel']:
        raise ValueError('Stock kernel differs')
    entries = read_newc(decompress(boot['ramdisk']))
    old = read_newc(decompress(parent_boot['ramdisk']))
    if (sha(entries['init']['data']) != build['init_sha256'] or
            entries['init']['data'] != (OUT / 'init-source').read_bytes() or
            set(entries) != set(old) or
            any(entries[name] != old[name] for name in old if name != 'init')):
        raise ValueError('Primary init-only change proof failed')
    if (old['init']['data'].count(OLD) != 1 or
            entries['init']['data'] != old['init']['data'].replace(OLD, NEW)):
        raise ValueError('Descriptor repair is not the sole init change')
    check = subprocess.run(['/usr/bin/busybox', 'sh', '-n', str(OUT / 'init-source')],
                           capture_output=True, timeout=10)
    if check.returncode:
        raise ValueError('BusyBox shell syntax refused')
    fixture = subprocess.run(['python3', str(ROOT / 'tools/test_persistent_openrc_v32_retry.py')],
                             capture_output=True, timeout=20)
    if fixture.returncode:
        raise ValueError('V32/V33 retry fixtures failed: ' + fixture.stderr.decode()[-500:])
    reference = json.loads((PORT / 'docs/avb-boot-model-results.json').read_text())
    if sha(MODEL.read_bytes()) != reference['binary_sha256']:
        raise ValueError('Pinned AVB model differs')
    cases = []
    for unlocked in (1, 0):
        run = subprocess.run([str(MODEL), str(STOCK_DIR), str(image), '0', str(unlocked)],
                             capture_output=True, text=True, timeout=20)
        if run.returncode:
            raise ValueError('AVB model failed')
        cases.append(json.loads(run.stdout))
    if not (cases[0]['slot_data_returned'] and cases[0]['boot_partitions_loaded'] == 1 and
            not cases[1]['slot_data_returned'] and cases[1]['boot_partitions_loaded'] == 0):
        raise ValueError('AVB model unlocked/locked behavior differs')
    result = {'state': 'offline-v33-validation-passed', 'created_ns': time.time_ns(),
              'image_sha256': build['image_sha256'], 'parent_v32_sha256': sha(parent),
              'stock_kernel_sha256': sha(stock_boot['kernel']),
              'supplement_identical_to_v32': True, 'changed_members': ['init'],
              'busybox_shell_syntax_passed': True, 'retry_fixtures_passed': True,
              'avb_cases': cases, 'phone_contacted': False, 'flash_performed': False,
              'limit': 'AOSP AVB model is not OnePlus LK; handset boot and Alpine PID 1 remain unproven.'}
    (OUT / 'validation.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'state': result['state'], 'result': str(OUT / 'validation.json')}))


if __name__ == '__main__':
    main()
