"""Build offline V46: cancel the startup timer only after proven local health."""
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
BASE = PORT / 'artifacts/wifi-failure-code-v45-offline'
OUT = PORT / 'artifacts/persistent-alpine-v46-offline'
V45_SHA = '228b290e478649b7b7c48a865365771b73dbac73aaac361f73a245ddff24ca87'
OLD_STAGES = b'|HANDOFF_BEGIN|HANDOFF_REFUSED|'
NEW_STAGES = b'|HANDOFF_BEGIN|TIMER_CANCELLED|HANDOFF_REFUSED|'
OLD_CALL = b'''            if [ -r /etc/lynx/persistent-openrc-handoff.sh ] &&
               . /etc/lynx/persistent-openrc-handoff.sh; then
                exec </dev/null 1>>/run/lynx/openrc-pid1-stdout.log 2>>/run/lynx/openrc-pid1-stderr.log
                lynx_persistent_openrc_handoff
            fi
'''
NEW_CALL = b'''            if [ -r /etc/lynx/persistent-openrc-handoff.sh ] &&
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
sys.path.insert(0, str(PORT))
from image_formats import read_boot_v4, read_newc, require
from ramdisk_codec import decompress


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    os.umask(0o077)
    require(not OUT.exists(), 'Refuse to replace V46 candidate')
    parent = (BASE / 'nord3-wifi-failure-code-v45-untested.img').read_bytes()
    require(sha(parent) == V45_SHA, 'V45 parent differs')
    boot = read_boot_v4(parent)
    primary = read_newc(decompress(boot['ramdisk']))
    old_init = primary['init']['data']
    require(old_init.count(OLD_STAGES) == 1 and old_init.count(OLD_CALL) == 1,
            'V45 local handoff path differs')
    init = old_init.replace(OLD_STAGES, NEW_STAGES).replace(OLD_CALL, NEW_CALL)
    require(subprocess.run(['busybox', 'sh', '-n'], input=init,
                           capture_output=True).returncode == 0,
            'V46 init shell syntax failed')
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
            f'V46 primary exceeds AVB-covered region by {len(loaded)-coverage} bytes')
    image = loaded.ljust(coverage, b'\0') + parent[coverage:]
    require(len(image) == len(parent) == 67_108_864,
            'V46 image size differs')
    checked = read_boot_v4(image)
    require(checked['kernel'] == boot['kernel'] and
            checked['cmdline'] == boot['cmdline'] and
            read_newc(decompress(checked['ramdisk'])) == primary and
            image[coverage:] == parent[coverage:],
            'V46 changed unrelated scope or failed roundtrip')
    OUT.mkdir(mode=0o700)
    target = OUT / 'nord3-persistent-alpine-v46-untested.img'
    target.write_bytes(image)
    target.chmod(0o600)
    (OUT / 'init-source').write_bytes(init)
    result = {'state': 'offline-persistent-alpine-built',
              'created_ns': time.time_ns(), 'parent_v45_sha256': V45_SHA,
              'image_sha256': sha(image), 'init_sha256': sha(init),
              'stock_kernel_sha256': sha(boot['kernel']),
              'supplement_sha256': sha(parent[coverage:]),
              'primary_changes': ['init'], 'supplement_unchanged': True,
              'partition_scope_if_trialled': ['boot_a'],
              'phone_contacted': False, 'flash_performed': False,
              'diagnostic_question': 'Can Lynx keep autonomous Alpine running after the V45 startup timer boundary with health watchers active?',
              'timer_cancel_condition': 'Three passing health checks, HANDOFF_BEGIN record, local helper loaded',
              'fallback': 'Parent power-off at uptime 300 if handoff returns',
              'autonomous_running_untested': True}
    (OUT / 'build-result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'state': result['state'],
                      'result': str(OUT / 'build-result.json')}))


if __name__ == '__main__':
    main()
