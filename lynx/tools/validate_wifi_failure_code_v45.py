"""Independently validate V45's bounded Wi-Fi failure-code diagnostic."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
PORT = ROOT / 'linux-port'
OUT = PORT / 'artifacts/wifi-failure-code-v45-offline'
PARENT = PORT / 'artifacts/local-openrc-probe-v44-offline/nord3-local-openrc-probe-v44-untested.img'
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
    target = OUT / 'nord3-wifi-failure-code-v45-untested.img'
    candidate, parent, v33, v19, stock = (path.read_bytes() for path in
        (target, PARENT, V33, V19, STOCK / 'boot.img'))
    if (build['state'] != 'offline-wifi-failure-code-built' or
            sha(candidate) != build['image_sha256'] or
            sha(parent) != build['parent_v44_sha256'] ==
            'c709158f962853ed86b6605ab2b3bb8866cae93518e3c762a239ebae0b6b3358' or
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
    old_stages = b'|WIFI_FAILED|UPTIME_120'
    new_stages = b'|WIFI_FAILED|WIFI_NO_RESULT|WIFI_ERR_[0-9]*|UPTIME_120'
    old_branch = b'''lynx_wifi_local_supervise || {
    lynx_bootdiag_append WIFI_FAILED || log 'V41_WIFI_FAILED_RECORD_FAILED'
    log 'V41_WIFI_FAILED; POWER_OFF_REQUESTED'
    $BB poweroff -f
    /bin/boot-proof-reboot
    stop
}
'''
    new_branch = b'''lynx_wifi_local_supervise || {
    lynx_bootdiag_append WIFI_FAILED || log 'V41_WIFI_FAILED_RECORD_FAILED'
    if [ -r /run/lynx/worker-result ]; then
        IFS= read -r v45_code < /run/lynx/worker-result || v45_code=''
        case "$v45_code" in
            ''|*[!0-9]*) log 'V45_WIFI_WORKER_CODE_INVALID' ;;
            *)
                [ "$v45_code" -le 255 ] &&
                    lynx_bootdiag_append "WIFI_ERR_$v45_code" || true
                ;;
        esac
    else
        lynx_bootdiag_append WIFI_NO_RESULT || true
    fi
    log 'V41_WIFI_FAILED; POWER_OFF_REQUESTED'
    $BB poweroff -f
    /bin/boot-proof-reboot
    stop
}
'''
    if (old_init.count(old_stages) != 1 or old_init.count(old_branch) != 1 or
            init != old_init.replace(old_stages, new_stages).replace(old_branch, new_branch) or
            sha(init) != build['init_sha256'] or
            b'lynx_persistent_openrc_handoff' not in init or
            b'$BB sleep 420' not in init):
        raise ValueError('V45 diagnostic delta differs')
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
    result = {'state': 'offline-v45-validation-passed',
              'created_ns': time.time_ns(), 'image_sha256': sha(candidate),
              'primary_changes': ['init'], 'supplement_unchanged': True,
              'rollback_v33_sha256': sha(v33),
              'rollback_v19_sha256': sha(v19), 'avb_cases': avb,
              'phone_contacted': False, 'flash_performed': False,
              'limit': 'Offline checks do not prove hardware boot or a specific Wi-Fi failure code.'}
    (OUT / 'validation.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'state': result['state'],
                      'result': str(OUT / 'validation.json')}))


if __name__ == '__main__':
    main()
