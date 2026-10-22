"""Build offline V43 with three-strike parent observation tolerance."""
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
BASE = PORT / 'artifacts/health-observe-v42-offline'
OUT = PORT / 'artifacts/health-tolerance-v43-offline'
V42_SHA = 'c7cb6b3a4a1619eb04bdc7a573eca7eb70644ea23d67028f8b5fa45ba8a7ce8e'
OLD = b'''    $BB sh /run/lynx/lynx-health-supervisor.sh --once || {
        lynx_bootdiag_append HEALTH_FAIL_POSTCHECK || true
        $BB poweroff -f
        /bin/boot-proof-reboot
        stop
    }
'''
NEW = b'''    if $BB sh /run/lynx/lynx-health-supervisor.sh --once > /run/lynx/v43-postcheck.log 2>&1; then
        v43_failures=0
    else
        v43_failures=$((v43_failures+1))
        log "V43_POSTCHECK_SAMPLE_FAILED count=$v43_failures"
        [ "$v43_failures" -lt 3 ] || {
            lynx_bootdiag_append HEALTH_FAIL_POSTCHECK || true
            $BB poweroff -f
            /bin/boot-proof-reboot
            stop
        }
    fi
'''
sys.path.insert(0, str(PORT))
from image_formats import read_boot_v4, read_newc, require
from ramdisk_codec import decompress


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    os.umask(0o077)
    require(not OUT.exists(), 'Refuse to replace V43 candidate')
    parent = (BASE / 'nord3-health-observe-v42-untested.img').read_bytes()
    require(sha(parent) == V42_SHA, 'V42 parent differs')
    boot = read_boot_v4(parent)
    primary = read_newc(decompress(boot['ramdisk']))
    old_init = primary['init']['data']
    require(old_init.count(OLD) == 1 and
            old_init.count(b'v43_failures=0') == 0,
            'V42 post-readiness path differs')
    init = old_init.replace(OLD, NEW).replace(b"log 'V41_HEALTH_READY; BUSYBOX_PID1_OBSERVATION_WINDOW'\n", b"log 'V41_HEALTH_READY; BUSYBOX_PID1_OBSERVATION_WINDOW'\nv43_failures=0\n")
    require(subprocess.run(['busybox', 'sh', '-n'], input=init,
                           capture_output=True).returncode == 0,
            'V43 init shell syntax failed')
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
            'V43 primary exceeds AVB-covered region')
    image = loaded.ljust(coverage, b'\0') + parent[coverage:]
    require(len(image) == len(parent) == 67_108_864,
            'V43 image size differs')
    checked = read_boot_v4(image)
    require(checked['kernel'] == boot['kernel'] and
            checked['cmdline'] == boot['cmdline'] and
            read_newc(decompress(checked['ramdisk'])) == primary and
            image[coverage:] == parent[coverage:],
            'V43 changed unrelated scope or failed roundtrip')
    OUT.mkdir(mode=0o700)
    target = OUT / 'nord3-health-tolerance-v43-untested.img'
    target.write_bytes(image)
    target.chmod(0o600)
    (OUT / 'init-source').write_bytes(init)
    result = {'state': 'offline-health-tolerance-built',
              'created_ns': time.time_ns(), 'parent_v42_sha256': V42_SHA,
              'image_sha256': sha(image), 'init_sha256': sha(init),
              'stock_kernel_sha256': sha(boot['kernel']),
              'supplement_sha256': sha(parent[coverage:]),
              'primary_changes': ['init'], 'supplement_unchanged': True,
              'partition_scope_if_trialled': ['boot_a'],
              'phone_contacted': False, 'flash_performed': False,
              'diagnostic_question': 'Can the parent tolerate isolated post-readiness failures while still shutting down after three consecutive failures?',
              'observation_limit_uptime_seconds': 300,
              'outer_poweroff_seconds_after_tail': 420}
    (OUT / 'build-result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'state': result['state'],
                      'result': str(OUT / 'build-result.json')}))


if __name__ == '__main__':
    main()
