"""Independently validate V41's init-only scope and exact rollback images."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
PORT = ROOT / 'linux-port'
OUT = PORT / 'artifacts/health-primary-v41-offline'
V39 = PORT / 'artifacts/delayed-health-v39-offline/nord3-delayed-health-v39-untested.img'
V33 = PORT / 'artifacts/persistent-openrc-v33-offline/nord3-persistent-openrc-v33-untested.img'
V19 = PORT / 'artifacts/busybox-wifi-ssh-twostage-v19/nord3-busybox-candidate.img'
STOCK = PORT / 'artifacts/stock-cph2493-August-eu-ota'
MODEL = ROOT / 'tools/avb-host/avb-boot-model'
MARKER = b'. /etc/lynx/wifi-runtime.sh || stop\n. /etc/lynx/wifi-local-supervise.sh || stop\n'
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
    image = OUT / 'nord3-health-primary-v41-untested.img'
    candidate, parent, v33, v19, stock = (path.read_bytes() for path in
        (image, V39, V33, V19, STOCK / 'boot.img'))
    if (build['state'] != 'offline-health-primary-built' or
            sha(candidate) != build['image_sha256'] or
            sha(parent) != build['parent_v39_sha256'] ==
            '0eaee951ce85918f5c6c4f6f88cf79ddba40485755df730103d390025a172f49' or
            sha(v33) != '1d65456979d8a48d31de77c987b8aaf9b5ac11af62c51d00fdaff68ad47e747f' or
            sha(v19) != '5ce2dbf8a7c132fa7e31f6be70aa76f83afe8c293e2cd5f02251a532486fd851'):
        raise ValueError('Candidate, parent, or rollback hash differs')
    boot, base, stock_boot = map(read_boot_v4, (candidate, parent, stock))
    if (boot['kernel'] != base['kernel'] or boot['kernel'] != stock_boot['kernel'] or
            boot['cmdline'] != base['cmdline']):
        raise ValueError('Kernel or command line differs')
    primary, old_primary = (read_newc(decompress(value['ramdisk']))
                            for value in (boot, base))
    if set(primary) != set(old_primary):
        raise ValueError('Primary member set differs')
    changes = [name for name in primary if primary[name] != old_primary[name]]
    if changes != ['init']:
        raise ValueError('Primary changes differ: ' + repr(changes))
    old_init = old_primary['init']['data']
    init = primary['init']['data']
    if (old_init.count(MARKER) != 1 or
            init[:len(old_init.split(MARKER)[0])] != old_init.split(MARKER)[0] or
            b'. /etc/lynx/autonomous-health-local-handoff.sh || stop' not in init or
            b'v41_retry' not in init or
            b'HEALTH_FAIL_POSTCHECK' not in init or
            b'HEALTH_READY' not in init or
            b'$BB sleep 420' not in init or
            b'lynx_persistent_openrc_handoff' in init or
            sha(init) != build['init_sha256']):
        raise ValueError('V41 init behavior differs')
    run(['busybox', 'sh', '-n'], init)
    recipe = json.loads((PORT / 'known-good-v19/recipe.json').read_text())
    coverage = recipe['coverage_bytes']
    if (candidate[coverage:] != parent[coverage:] or
            sha(candidate[coverage:]) != build['supplement_sha256'] or
            primary['etc/lynx/payload-bytes'] != old_primary['etc/lynx/payload-bytes'] or
            primary['etc/lynx/payload-sha256'] != old_primary['etc/lynx/payload-sha256']):
        raise ValueError('Supplement or payload metadata changed')
    reference = json.loads((PORT / 'docs/avb-boot-model-results.json').read_text())
    if sha(MODEL.read_bytes()) != reference['binary_sha256']:
        raise ValueError('AVB model differs')
    avb = [json.loads(run([str(MODEL), str(STOCK), str(image), '0', str(unlocked)]))
           for unlocked in (1, 0)]
    if (not avb[0]['slot_data_returned'] or avb[0]['boot_partitions_loaded'] != 1 or
            avb[1]['slot_data_returned'] or avb[1]['boot_partitions_loaded'] != 0):
        raise ValueError('AVB model behavior differs')
    result = {'state': 'offline-v41-validation-passed',
              'created_ns': time.time_ns(), 'image_sha256': sha(candidate),
              'primary_changes': changes, 'supplement_unchanged': True,
              'rollback_v33_sha256': sha(v33),
              'rollback_v19_sha256': sha(v19), 'avb_cases': avb,
              'phone_contacted': False, 'flash_performed': False,
              'limit': 'Offline checks do not prove hardware boot or health success.'}
    (OUT / 'validation.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'state': result['state'],
                      'result': str(OUT / 'validation.json')}))


if __name__ == '__main__':
    main()
