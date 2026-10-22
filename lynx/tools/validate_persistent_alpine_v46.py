"""Independently validate V46's conditional startup timer cancellation."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
PORT = ROOT / 'linux-port'
OUT = PORT / 'artifacts/persistent-alpine-v46-offline'
PARENT = PORT / 'artifacts/wifi-failure-code-v45-offline/nord3-wifi-failure-code-v45-untested.img'
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
    target = OUT / 'nord3-persistent-alpine-v46-untested.img'
    candidate, parent, v33, v19, stock = (path.read_bytes() for path in
        (target, PARENT, V33, V19, STOCK / 'boot.img'))
    if (build['state'] != 'offline-persistent-alpine-built' or
            sha(candidate) != build['image_sha256'] or
            sha(parent) != build['parent_v45_sha256'] ==
            '228b290e478649b7b7c48a865365771b73dbac73aaac361f73a245ddff24ca87' or
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
    old_stages = b'|HANDOFF_BEGIN|HANDOFF_REFUSED|'
    new_stages = b'|HANDOFF_BEGIN|TIMER_CANCELLED|HANDOFF_REFUSED|'
    old_call = b'''            if [ -r /etc/lynx/persistent-openrc-handoff.sh ] &&
               . /etc/lynx/persistent-openrc-handoff.sh; then
                exec </dev/null 1>>/run/lynx/openrc-pid1-stdout.log 2>>/run/lynx/openrc-pid1-stderr.log
                lynx_persistent_openrc_handoff
            fi
'''
    new_call = b'''            if [ -r /etc/lynx/persistent-openrc-handoff.sh ] &&
               . /etc/lynx/persistent-openrc-handoff.sh; then
                kill "$v40_outer_timer" || {
                    log 'V46_OUTER_TIMER_CANCEL_FAILED; POWER_OFF_REQUESTED'
                    $BB poweroff -f
                    /bin/boot-proof-reboot
                    stop
                }
                wait "$v40_outer_timer" 2>/dev/null || true
                lynx_bootdiag_append TIMER_CANCELLED || {
                    log 'V46_TIMER_CANCEL_RECORD_FAILED; POWER_OFF_REQUESTED'
                    $BB poweroff -f
                    /bin/boot-proof-reboot
                    stop
                }
                log 'V46_OUTER_TIMER_CANCELLED_AFTER_HEALTH'
                exec </dev/null 1>>/run/lynx/openrc-pid1-stdout.log 2>>/run/lynx/openrc-pid1-stderr.log
                lynx_persistent_openrc_handoff
            fi
'''
    if (old_init.count(old_stages) != 1 or old_init.count(old_call) != 1 or
            init != old_init.replace(old_stages, new_stages).replace(old_call, new_call) or
            sha(init) != build['init_sha256'] or
            b'$BB sleep 420' not in init or
            b'[ "$v40_uptime" -lt 300 ] || break' not in init or
            b'v44_passes=$((v44_passes+1))' not in init or
            b'lynx_persistent_openrc_handoff' not in init):
        raise ValueError('V46 timer cancellation delta differs')
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
    result = {'state': 'offline-v46-validation-passed',
              'created_ns': time.time_ns(), 'image_sha256': sha(candidate),
              'primary_changes': ['init'], 'supplement_unchanged': True,
              'rollback_v33_sha256': sha(v33),
              'rollback_v19_sha256': sha(v19), 'avb_cases': avb,
              'phone_contacted': False, 'flash_performed': False,
              'limit': 'Offline checks do not prove timer cancellation, cold boot or sustained Alpine health.'}
    (OUT / 'validation.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'state': result['state'],
                      'result': str(OUT / 'validation.json')}))


if __name__ == '__main__':
    main()
