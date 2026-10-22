"""Independently check V44's bounded local OpenRC handoff image."""
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
PORT = ROOT / 'linux-port'
OUT = PORT / 'artifacts/local-openrc-probe-v44-offline'
PARENT = PORT / 'artifacts/health-tolerance-v43-offline/nord3-health-tolerance-v43-untested.img'
V33 = PORT / 'artifacts/persistent-openrc-v33-offline/nord3-persistent-openrc-v33-untested.img'
V19 = PORT / 'artifacts/busybox-wifi-ssh-twostage-v19/nord3-busybox-candidate.img'
STOCK = PORT / 'artifacts/stock-cph2493-August-eu-ota'
MODEL = ROOT / 'tools/avb-host/avb-boot-model'
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
    target = OUT / 'nord3-local-openrc-probe-v44-untested.img'
    candidate, parent, v33, v19, stock = (path.read_bytes() for path in
        (target, PARENT, V33, V19, STOCK / 'boot.img'))
    if (build['state'] != 'offline-local-openrc-probe-built' or
            sha(candidate) != build['image_sha256'] or
            sha(parent) != build['parent_v43_sha256'] ==
            '4c088d2b4aca070510291322b9a809947100cecf0909bc458727914f5afbd875' or
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
    marker = b"log 'V41_HEALTH_READY; BUSYBOX_PID1_OBSERVATION_WINDOW'\n"
    old_stages = b'|HEALTH_READY|CHARGER_ON|END)'
    new_stages = b'|HEALTH_READY|HANDOFF_BEGIN|HANDOFF_REFUSED|CHARGER_ON|END)'
    if old_init.count(marker) != 1 or old_init.count(old_stages) != 1:
        raise ValueError('V43 source anchors differ')
    tail = (PORT / 'lynx-v44-local-openrc-tail.sh').read_bytes()
    expected_untrimmed = old_init.split(marker)[0].replace(old_stages, new_stages) + tail
    lines = expected_untrimmed.splitlines(keepends=True)
    comments = [line for line in lines if line.startswith(b'#') and not line.startswith(b'#!')]
    expected = b''.join(line for line in lines if line not in comments)
    if (init != expected or len(comments) != 12 or
            sha(init) != build['init_sha256'] or
            b'$BB sleep 420' not in init or
            b'[ "$v40_uptime" -lt 300 ] || break' not in init or
            b'lynx_persistent_openrc_handoff' not in init or
            b'lynx_bootdiag_append HANDOFF_BEGIN' not in init or
            b'v44_failures' not in init or b'v44_passes' not in init):
        raise ValueError('V44 local handoff delta differs')
    run(['busybox', 'sh', '-n'], init)
    recipe = json.loads((PORT / 'known-good-v19/recipe.json').read_text())
    coverage, offset = recipe['coverage_bytes'], recipe['payload_offset']
    if (candidate[coverage:] != parent[coverage:] or
            sha(candidate[coverage:]) != build['supplement_sha256']):
        raise ValueError('Supplement differs')
    length = int(primary['etc/lynx/payload-bytes']['data'])
    payload = candidate[offset:offset+length]
    if sha(payload) != primary['etc/lynx/payload-sha256']['data'].decode().strip():
        raise ValueError('Supplement manifest differs')
    supplement = read_newc(gzip.decompress(payload))
    helper = supplement['etc/lynx/persistent-openrc-handoff.sh']['data']
    if (sha(helper) != build['local_handoff_helper_sha256'] or
            helper != (PORT / 'persistent-openrc-handoff-v34.sh').read_bytes() or
            b'LYNX_OPENRC_AUTHORITY=local' not in helper):
        raise ValueError('Local guard or handoff helper differs')
    reference = json.loads((PORT / 'docs/avb-boot-model-results.json').read_text())
    if sha(MODEL.read_bytes()) != reference['binary_sha256']:
        raise ValueError('AVB model binary differs')
    avb = [json.loads(run([str(MODEL), str(STOCK), str(target), '0', str(unlocked)]))
           for unlocked in (1, 0)]
    if (not avb[0]['slot_data_returned'] or avb[0]['boot_partitions_loaded'] != 1 or
            avb[1]['slot_data_returned'] or avb[1]['boot_partitions_loaded'] != 0):
        raise ValueError('AVB model behavior differs')
    result = {'state': 'offline-v44-validation-passed',
              'created_ns': time.time_ns(), 'image_sha256': sha(candidate),
              'primary_changes': ['init'], 'supplement_unchanged': True,
              'rollback_v33_sha256': sha(v33),
              'rollback_v19_sha256': sha(v19), 'avb_cases': avb,
              'phone_contacted': False, 'flash_performed': False,
              'limit': 'Offline checks do not prove autonomous handoff or OpenRC behavior.'}
    (OUT / 'validation.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'state': result['state'],
                      'result': str(OUT / 'validation.json')}))


if __name__ == '__main__':
    main()
