"""Independently validate V40's parent retry, image scope and rollbacks."""
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
PORT = ROOT / 'linux-port'
OUT = PORT / 'artifacts/health-parent-retry-v40-offline'
V39 = PORT / 'artifacts/delayed-health-v39-offline/nord3-delayed-health-v39-untested.img'
V33 = PORT / 'artifacts/persistent-openrc-v33-offline/nord3-persistent-openrc-v33-untested.img'
V19 = PORT / 'artifacts/busybox-wifi-ssh-twostage-v19/nord3-busybox-candidate.img'
STOCK = PORT / 'artifacts/stock-cph2493-August-eu-ota'
MODEL = ROOT / 'tools/avb-host/avb-boot-model'
HANDOFF = 'etc/lynx/autonomous-health-local-handoff.sh'
MARKER = b'. /etc/lynx/wifi-runtime.sh || stop\n. /etc/lynx/wifi-local-supervise.sh || stop\n'
sys.path.insert(0, str(PORT))
from image_formats import read_boot_v4, read_newc
from ramdisk_codec import decompress


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def run(argv, *, data=None):
    result = subprocess.run(argv, input=data, capture_output=True, timeout=30)
    if result.returncode:
        raise ValueError('Validation failed: ' + str(argv) + ' ' +
                         result.stderr[-300:].decode(errors='replace'))
    return result.stdout


def main():
    build = json.loads((OUT / 'build-result.json').read_text())
    image = OUT / 'nord3-health-parent-retry-v40-untested.img'
    candidate, parent, v33, v19, stock = (path.read_bytes() for path in
        (image, V39, V33, V19, STOCK / 'boot.img'))
    if (build['state'] != 'offline-health-parent-retry-built' or
            sha(candidate) != build['image_sha256'] or
            sha(parent) != build['parent_v39_sha256'] ==
            '0eaee951ce85918f5c6c4f6f88cf79ddba40485755df730103d390025a172f49' or
            sha(v33) != '1d65456979d8a48d31de77c987b8aaf9b5ac11af62c51d00fdaff68ad47e747f' or
            sha(v19) != '5ce2dbf8a7c132fa7e31f6be70aa76f83afe8c293e2cd5f02251a532486fd851'):
        raise ValueError('Candidate, parent or rollback image differs')
    boot, base, stock_boot = map(read_boot_v4, (candidate, parent, stock))
    if (boot['kernel'] != base['kernel'] or boot['kernel'] != stock_boot['kernel'] or
            boot['cmdline'] != base['cmdline']):
        raise ValueError('Kernel or command line differs')
    primary, old_primary = (read_newc(decompress(value['ramdisk']))
                            for value in (boot, base))
    if set(primary) != set(old_primary):
        raise ValueError('Primary member set differs')
    for name, old in old_primary.items():
        if name not in ('init', 'etc/lynx/payload-bytes', 'etc/lynx/payload-sha256') and primary[name] != old:
            raise ValueError('Unrelated primary member changed: ' + name)
    tail = (PORT / 'lynx-v40-health-retry-tail.sh').read_bytes()
    handoff = (PORT / 'autonomous-health-local-handoff-v40.sh').read_bytes()
    if (old_primary['init']['data'].count(MARKER) != 1 or
            primary['init']['data'] != old_primary['init']['data'].split(MARKER)[0] + tail or
            not tail.startswith(MARKER) or
            b'lynx_persistent_openrc_handoff' in tail or
            b'$BB sleep 420' not in tail or
            b'[ "$v40_uptime" -lt 190 ] || break' not in tail or
            b'HEALTH_FAIL_POSTCHECK' not in tail or
            b'LYNX_LOCAL_HEALTH_FAILURE' not in tail or
            b'$BB sh /run/lynx/lynx-health-supervisor.sh --once' not in tail):
        raise ValueError('V40 init-only health diagnostic differs')
    if (b'for local_postcheck_attempt in 1 2 3' not in handoff or
            b'LYNX_LOCAL_HEALTH_FAILURE=postcheck' not in handoff or
            b'LYNX_LOCAL_HEALTH_FAILURE=watcher' not in handoff or
            b'LYNX_LOCAL_HEALTH_FAILURE=battery' not in handoff or
            b'LYNX_LOCAL_HEALTH_FAILURE=thermal' not in handoff or
            b'LOCAL_HEALTH_BOOT_READY; BUSYBOX_RESCUE_PID1_ACTIVE' not in handoff):
        raise ValueError('V40 parent health retry differs')
    run(['busybox', 'sh', '-n'], data=primary['init']['data'])
    run(['busybox', 'sh', '-n'], data=handoff)
    recipe = json.loads((PORT / 'known-good-v19/recipe.json').read_text())
    coverage, offset = recipe['coverage_bytes'], recipe['payload_offset']
    if candidate[coverage:offset] != parent[coverage:offset]:
        raise ValueError('AVB footer or gap differs')
    old_len = int(old_primary['etc/lynx/payload-bytes']['data'])
    new_len = int(primary['etc/lynx/payload-bytes']['data'])
    old_payload = parent[offset:offset + old_len]
    new_payload = candidate[offset:offset + new_len]
    if (sha(new_payload) != build['payload_sha256'] or
            sha(new_payload) != primary['etc/lynx/payload-sha256']['data'].decode().strip() or
            candidate[offset + max(old_len, new_len):] !=
            parent[offset + max(old_len, new_len):]):
        raise ValueError('Supplement hash, footer or trailing bytes differ')
    old_supplement = read_newc(gzip.decompress(old_payload))
    supplement = read_newc(gzip.decompress(new_payload))
    if set(supplement) != set(old_supplement):
        raise ValueError('Supplement member set differs')
    for name, old in old_supplement.items():
        if name != HANDOFF and supplement[name] != old:
            raise ValueError('Unrelated supplement member changed: ' + name)
    if (supplement[HANDOFF]['data'] != handoff or
            sha(handoff) != build['health_handoff_v40_sha256'] or
            old_supplement[HANDOFF]['data'] !=
            (PORT / 'autonomous-health-local-handoff.sh').read_bytes()):
        raise ValueError('Health handoff source or old provenance differs')
    reference = json.loads((PORT / 'docs/avb-boot-model-results.json').read_text())
    if sha(MODEL.read_bytes()) != reference['binary_sha256']:
        raise ValueError('AVB model differs')
    avb = [json.loads(run([str(MODEL), str(STOCK), str(image), '0', str(unlocked)]))
           for unlocked in (1, 0)]
    if (not avb[0]['slot_data_returned'] or avb[0]['boot_partitions_loaded'] != 1 or
            avb[1]['slot_data_returned'] or avb[1]['boot_partitions_loaded'] != 0):
        raise ValueError('AVB model behavior differs')
    result = {'state': 'offline-v40-validation-passed',
              'created_ns': time.time_ns(), 'image_sha256': sha(candidate),
              'stock_kernel_sha256': sha(boot['kernel']),
              'primary_changes': ['init', 'payload-bytes', 'payload-sha256'],
              'supplement_changes': [HANDOFF],
              'rollback_v33_sha256': sha(v33),
              'rollback_v19_sha256': sha(v19),
              'avb_cases': avb, 'phone_contacted': False,
              'flash_performed': False,
              'limit': 'Offline checks do not prove V40 hardware boot, parent health check, persistent logging, or power-off.'}
    (OUT / 'validation.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'state': result['state'],
                      'result': str(OUT / 'validation.json')}))


if __name__ == '__main__':
    main()
