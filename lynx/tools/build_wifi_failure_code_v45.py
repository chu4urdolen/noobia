"""Build offline V45: retain V44 handoff, persist bounded Wi-Fi failure code."""
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import time

import build_health_stage_candidate as stage

ROOT, PORT = stage.ROOT, stage.PORT
BASE = PORT / 'artifacts/local-openrc-probe-v44-offline'
OUT = PORT / 'artifacts/wifi-failure-code-v45-offline'
V44_SHA = 'c709158f962853ed86b6605ab2b3bb8866cae93518e3c762a239ebae0b6b3358'
OLD_STAGES = b'|WIFI_FAILED|UPTIME_120'
NEW_STAGES = b'|WIFI_FAILED|WIFI_NO_RESULT|WIFI_ERR_[0-9]*|UPTIME_120'
OLD_FAILURE = b'''lynx_wifi_local_supervise || {
    lynx_bootdiag_append WIFI_FAILED || log 'V41_WIFI_FAILED_RECORD_FAILED'
    log 'V41_WIFI_FAILED; POWER_OFF_REQUESTED'
    $BB poweroff -f
    /bin/boot-proof-reboot
    stop
}
'''
NEW_FAILURE = b'''lynx_wifi_local_supervise || {
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
sys.path.insert(0, str(PORT))
from image_formats import read_boot_v4, read_newc, require
from ramdisk_codec import decompress


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    os.umask(0o077)
    require(not OUT.exists(), 'Refuse to replace V45 candidate')
    parent = (BASE / 'nord3-local-openrc-probe-v44-untested.img').read_bytes()
    require(sha(parent) == V44_SHA, 'V44 parent differs')
    boot = read_boot_v4(parent)
    primary = read_newc(decompress(boot['ramdisk']))
    old_init = primary['init']['data']
    require(old_init.count(OLD_STAGES) == 1 and
            old_init.count(OLD_FAILURE) == 1,
            'V44 failure path differs')
    init = old_init.replace(OLD_STAGES, NEW_STAGES).replace(OLD_FAILURE, NEW_FAILURE)
    require(subprocess.run(['busybox', 'sh', '-n'], input=init,
                           capture_output=True).returncode == 0,
            'V45 init shell syntax failed')
    primary['init'] = {**primary['init'], 'data': init}
    ramdisk = stage.packed(primary)
    header = bytearray(parent[:1584])
    struct.pack_into('<I', header, 12, len(ramdisk))
    align = lambda value: (value + 4095) // 4096 * 4096
    loaded = (bytes(header).ljust(4096, b'\0') +
              boot['kernel'].ljust(align(len(boot['kernel'])), b'\0') +
              ramdisk.ljust(align(len(ramdisk)), b'\0'))
    recipe = json.loads((PORT / 'known-good-v19/recipe.json').read_text())
    coverage = recipe['coverage_bytes']
    require(len(loaded) <= coverage <= recipe['payload_offset'],
            f'V45 primary exceeds AVB-covered region by {len(loaded)-coverage} bytes')
    image = loaded.ljust(coverage, b'\0') + parent[coverage:]
    require(len(image) == len(parent) == 67_108_864,
            'V45 image size differs')
    checked = read_boot_v4(image)
    require(checked['kernel'] == boot['kernel'] and
            checked['cmdline'] == boot['cmdline'] and
            read_newc(decompress(checked['ramdisk'])) == primary and
            image[coverage:] == parent[coverage:],
            'V45 changed unrelated scope or failed roundtrip')
    OUT.mkdir(mode=0o700)
    target = OUT / 'nord3-wifi-failure-code-v45-untested.img'
    target.write_bytes(image)
    target.chmod(0o600)
    (OUT / 'init-source').write_bytes(init)
    result = {'state': 'offline-wifi-failure-code-built',
              'created_ns': time.time_ns(), 'parent_v44_sha256': V44_SHA,
              'image_sha256': sha(image), 'init_sha256': sha(init),
              'stock_kernel_sha256': sha(boot['kernel']),
              'supplement_sha256': sha(parent[coverage:]),
              'primary_changes': ['init'], 'supplement_unchanged': True,
              'partition_scope_if_trialled': ['boot_a'],
              'phone_contacted': False, 'flash_performed': False,
              'diagnostic_question': 'If Wi-Fi fails before handoff, which worker code is returned?',
              'outer_poweroff_seconds_after_tail': 420,
              'bounded_trial': True}
    (OUT / 'build-result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'state': result['state'],
                      'result': str(OUT / 'build-result.json')}))


if __name__ == '__main__':
    main()
