"""Independently validate the private V30 boot image; no phone contact."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
PORT = ROOT / 'linux-port'
OUT = PORT / 'artifacts/persistent-openrc-v30-offline'
STOCK = PORT / 'artifacts/stock-cph2493-August-eu-ota'
MODEL = ROOT / 'tools/avb-host/avb-boot-model'
sys.path.insert(0, str(PORT))
from image_formats import read_boot_v4, read_newc
from ramdisk_codec import decompress


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    build = json.loads((OUT / 'build-result.json').read_text())
    image = OUT / 'nord3-persistent-openrc-v30-untested.img'
    data = image.read_bytes()
    stock = (STOCK / 'boot.img').read_bytes()
    if (build['state'] != 'offline-persistent-openrc-candidate-built' or
            sha(data) != build['image_sha256'] or
            sha(stock) != 'a67f03d7b826b834c23653b67eaa6efa971eb70ef8af19eee4d33fb5fc7fe995' or
            read_boot_v4(data)['kernel'] != read_boot_v4(stock)['kernel']):
        raise ValueError('Candidate or stock kernel identity differs')
    entries = read_newc(decompress(read_boot_v4(data)['ramdisk']))
    if (sha(entries['init']['data']) != build['init_sha256'] or
            entries['init']['data'] != (OUT / 'init-source').read_bytes()):
        raise ValueError('Init source differs from packed image')
    scripts = [PORT / 'persistent-openrc-handoff-v30.sh', PORT / 'openrc-handoff-guard.sh',
               OUT / 'init-source']
    for script in scripts:
        check = subprocess.run(['sh', '-n', str(script)], capture_output=True, timeout=10)
        if check.returncode:
            raise ValueError('Shell syntax refused: ' + str(script))
    reference = json.loads((PORT / 'docs/avb-boot-model-results.json').read_text())
    if sha(MODEL.read_bytes()) != reference['binary_sha256']:
        raise ValueError('Pinned AVB model binary differs')
    cases = []
    for unlocked in (1, 0):
        process = subprocess.run([str(MODEL), str(STOCK), str(image), '0', str(unlocked)],
                                 capture_output=True, text=True, timeout=20)
        if process.returncode:
            raise ValueError('AVB model failed')
        case = json.loads(process.stdout)
        case['diagnostics'] = process.stderr
        cases.append(case)
    if not (cases[0]['slot_data_returned'] and cases[0]['boot_partitions_loaded'] == 1 and
            not cases[1]['slot_data_returned'] and cases[1]['boot_partitions_loaded'] == 0):
        raise ValueError('AVB unlocked/locked model behavior differs')
    result = {'state': 'offline-candidate-validation-passed', 'created_ns': time.time_ns(),
              'image_sha256': build['image_sha256'],
              'stock_kernel_sha256': sha(read_boot_v4(stock)['kernel']),
              'shell_syntax_passed': True, 'avb_cases': cases,
              'phone_contacted': False, 'flash_performed': False,
              'limits': 'AOSP AVB model is not proprietary OnePlus LK; this does not prove handset boot or OpenRC PID 1.'}
    (OUT / 'validation.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'state': result['state'], 'result': str(OUT / 'validation.json')}))


if __name__ == '__main__':
    main()
