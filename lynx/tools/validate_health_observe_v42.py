"""Independently validate V42's exact post-readiness log-only change."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
PORT = ROOT / 'linux-port'
OUT = PORT / 'artifacts/health-observe-v42-offline'
V41 = PORT / 'artifacts/health-primary-v41-offline/nord3-health-primary-v41-untested.img'
V33 = PORT / 'artifacts/persistent-openrc-v33-offline/nord3-persistent-openrc-v33-untested.img'
V19 = PORT / 'artifacts/busybox-wifi-ssh-twostage-v19/nord3-busybox-candidate.img'
STOCK = PORT / 'artifacts/stock-cph2493-August-eu-ota'
MODEL = ROOT / 'tools/avb-host/avb-boot-model'
OLD = b"log 'V41_HEALTH_POSTCHECK_FAILED; POWER_OFF_REQUESTED'\n"
NEW = b"lynx_bootdiag_append HEALTH_FAIL_POSTCHECK || true\n"
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
    target = OUT / 'nord3-health-observe-v42-untested.img'
    candidate, parent, v33, v19, stock = (path.read_bytes() for path in
        (target, V41, V33, V19, STOCK / 'boot.img'))
    if (build['state'] != 'offline-health-observe-built' or
            sha(candidate) != build['image_sha256'] or
            sha(parent) != build['parent_v41_sha256'] ==
            '9a1bb4e1a3a5cc89ff910dbdc2013868a28063c2a3dbc1fa7f1f0f040d521776' or
            sha(v33) != '1d65456979d8a48d31de77c987b8aaf9b5ac11af62c51d00fdaff68ad47e747f' or
            sha(v19) != '5ce2dbf8a7c132fa7e31f6be70aa76f83afe8c293e2cd5f02251a532486fd851'):
        raise ValueError('Candidate, parent or rollback hash differs')
    boot, base, stock_boot = map(read_boot_v4, (candidate, parent, stock))
    if (boot['kernel'] != base['kernel'] or
            boot['kernel'] != stock_boot['kernel'] or
            boot['cmdline'] != base['cmdline']):
        raise ValueError('Kernel or command line differs')
    primary, old_primary = (read_newc(decompress(value['ramdisk']))
                            for value in (boot, base))
    if (set(primary) != set(old_primary) or
            [name for name in primary if primary[name] != old_primary[name]] != ['init']):
        raise ValueError('Primary member scope differs')
    old_init, init = old_primary['init']['data'], primary['init']['data']
    if (old_init.count(OLD) != 1 or init != old_init.replace(OLD, NEW) or
            sha(init) != build['init_sha256'] or
            b'HEALTH_FAIL_POSTCHECK' not in init or
            b'$BB sleep 420' not in init or
            b'[ "$v40_uptime" -lt 300 ] || break' not in init):
        raise ValueError('Post-readiness marker delta differs')
    run(['busybox', 'sh', '-n'], init)
    recipe = json.loads((PORT / 'known-good-v19/recipe.json').read_text())
    coverage = recipe['coverage_bytes']
    if (candidate[coverage:] != parent[coverage:] or
            sha(candidate[coverage:]) != build['supplement_sha256']):
        raise ValueError('Supplement differs')
    reference = json.loads((PORT / 'docs/avb-boot-model-results.json').read_text())
    if sha(MODEL.read_bytes()) != reference['binary_sha256']:
        raise ValueError('AVB model binary differs')
    avb = [json.loads(run([str(MODEL), str(STOCK), str(target), '0', str(unlocked)]))
           for unlocked in (1, 0)]
    if (not avb[0]['slot_data_returned'] or avb[0]['boot_partitions_loaded'] != 1 or
            avb[1]['slot_data_returned'] or avb[1]['boot_partitions_loaded'] != 0):
        raise ValueError('AVB model behavior differs')
    result = {'state': 'offline-v42-validation-passed',
              'created_ns': time.time_ns(), 'image_sha256': sha(candidate),
              'primary_changes': ['init'], 'supplement_unchanged': True,
              'rollback_v33_sha256': sha(v33),
              'rollback_v19_sha256': sha(v19), 'avb_cases': avb,
              'phone_contacted': False, 'flash_performed': False,
              'limit': 'Offline checks do not prove V42 hardware boot or identify the previous stop.'}
    (OUT / 'validation.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'state': result['state'],
                      'result': str(OUT / 'validation.json')}))


if __name__ == '__main__':
    main()
