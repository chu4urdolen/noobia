"""Independently validate V37 image scope, boot model and rollback inputs."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
PORT = ROOT / 'linux-port'
OUT = PORT / 'artifacts/wifi-only-window-v37-offline'
V36 = PORT / 'artifacts/local-cooldown-v36-offline/nord3-local-cooldown-v36-untested.img'
V33 = PORT / 'artifacts/persistent-openrc-v33-offline/nord3-persistent-openrc-v33-untested.img'
V19 = PORT / 'artifacts/busybox-wifi-ssh-twostage-v19/nord3-busybox-candidate.img'
STOCK = PORT / 'artifacts/stock-cph2493-August-eu-ota'
MODEL = ROOT / 'tools/avb-host/avb-boot-model'
MARKER = b'. /etc/lynx/wifi-runtime.sh || stop\n. /etc/lynx/wifi-local-supervise.sh || stop\n'
sys.path.insert(0, str(PORT))
from image_formats import read_boot_v4, read_newc
from ramdisk_codec import decompress


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def run(argv, *, data=None, timeout=30):
    result = subprocess.run(argv, input=data, capture_output=True, timeout=timeout)
    if result.returncode:
        raise ValueError('Validation failed: ' + str(argv) + ' ' +
                         result.stderr[-300:].decode(errors='replace'))
    return result.stdout


def main():
    build = json.loads((OUT / 'build-result.json').read_text())
    image = OUT / 'nord3-wifi-only-window-v37-untested.img'
    candidate, parent, v33, v19, stock = (path.read_bytes() for path in
        (image, V36, V33, V19, STOCK / 'boot.img'))
    if (build['state'] != 'offline-wifi-only-diagnostic-built' or
            sha(candidate) != build['image_sha256'] or
            sha(parent) != build['parent_v36_sha256'] or
            sha(v33) != '1d65456979d8a48d31de77c987b8aaf9b5ac11af62c51d00fdaff68ad47e747f' or
            sha(v19) != '5ce2dbf8a7c132fa7e31f6be70aa76f83afe8c293e2cd5f02251a532486fd851'):
        raise ValueError('Candidate, parent or rollback image differs')
    boot, base, stock_boot = map(read_boot_v4, (candidate, parent, stock))
    if (boot['kernel'] != base['kernel'] or boot['kernel'] != stock_boot['kernel'] or
            boot['cmdline'] != base['cmdline']):
        raise ValueError('Kernel or cmdline differs')
    entries = read_newc(decompress(boot['ramdisk']))
    old = read_newc(decompress(base['ramdisk']))
    if (set(entries) != set(old) or
            any(entries[name] != old[name] for name in old if name != 'init')):
        raise ValueError('Changes extend beyond primary init')
    tail = (PORT / 'lynx-v37-wifi-window-tail.sh').read_bytes()
    init = entries['init']['data']
    if (old['init']['data'].count(MARKER) != 1 or
            init != old['init']['data'].split(MARKER)[0] + tail or
            not tail.startswith(MARKER) or
            b'WIFI_ONLY_SSH_READY; HEALTH_NOT_STARTED' not in tail or
            b'WIFI_ONLY_OBSERVATION_COMPLETE; POWER_OFF_REQUESTED' not in tail or
            b'lynx_autonomous_health_local_handoff' in tail or
            b'lynx_persistent_openrc_handoff' in tail or
            b'health-bootstrap' in tail or
            b'[ "$wifi_only_uptime" -lt 190 ] || break' not in tail or
            b'$BB sleep 230' not in tail):
        raise ValueError('Wi-Fi-only tail or bounded power-off differs')
    run(['busybox', 'sh', '-n'], data=init)
    recipe = json.loads((PORT / 'known-good-v19/recipe.json').read_text())
    if candidate[recipe['coverage_bytes']:] != parent[recipe['coverage_bytes']:]:
        raise ValueError('Supplement, AVB footer or trailing bytes differ')
    reference = json.loads((PORT / 'docs/avb-boot-model-results.json').read_text())
    if sha(MODEL.read_bytes()) != reference['binary_sha256']:
        raise ValueError('AVB model differs')
    avb = [json.loads(run([str(MODEL), str(STOCK), str(image), '0', str(unlocked)]))
           for unlocked in (1, 0)]
    if (not avb[0]['slot_data_returned'] or avb[0]['boot_partitions_loaded'] != 1 or
            avb[1]['slot_data_returned'] or avb[1]['boot_partitions_loaded'] != 0):
        raise ValueError('AVB model behavior differs')
    result = {'state': 'offline-v37-validation-passed',
              'created_ns': time.time_ns(), 'image_sha256': sha(candidate),
              'stock_kernel_sha256': sha(boot['kernel']),
              'init_only_change_from_v36': True, 'supplement_unchanged': True,
              'rollback_v33_sha256': sha(v33), 'rollback_v19_sha256': sha(v19),
              'avb_cases': avb, 'phone_contacted': False,
              'flash_performed': False,
              'limit': 'Offline validation does not prove MTK boot, Wi-Fi persistence, or power-off on Lynx.'}
    (OUT / 'validation.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'state': result['state'],
                      'result': str(OUT / 'validation.json')}))


if __name__ == '__main__':
    main()
