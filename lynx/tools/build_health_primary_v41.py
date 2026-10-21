"""Build offline V41: V40 parent retry with V39 supplement unchanged."""
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
BASE = PORT / 'artifacts/delayed-health-v39-offline'
OUT = PORT / 'artifacts/health-primary-v41-offline'
V39_SHA = '0eaee951ce85918f5c6c4f6f88cf79ddba40485755df730103d390025a172f49'
MARKER = b'. /etc/lynx/wifi-runtime.sh || stop\n. /etc/lynx/wifi-local-supervise.sh || stop\n'
OLD_SOURCE = b'. /etc/lynx/autonomous-health-local-handoff.sh || stop\n'
FAIL_START = b'lynx_autonomous_health_local_handoff || {\n'
FAIL_END = b'[ -f /run/lynx/health-bootstrap/ready ] || stop\n'
RETRY = b'''if ! lynx_autonomous_health_local_handoff; then
    v41_reason=HEALTH_FAIL_CHILD
    if [ -f /run/lynx/health-bootstrap/ready ] &&
       [ "$($BB cat /run/lynx/health-bootstrap-child-result 2>/dev/null)" = 0 ]; then
        v41_reason=HEALTH_FAIL_POSTCHECK
        v41_retry=0
        while [ "$v41_retry" -lt 2 ]; do
            $BB sleep 1
            if $BB sh /run/lynx/lynx-health-supervisor.sh --once > /run/lynx/v41-parent-postcheck.log 2>&1; then
                v41_reason=HEALTH_READY
                break
            fi
            v41_retry=$((v41_retry+1))
        done
    fi
    if [ "$v41_reason" != HEALTH_READY ]; then
        lynx_bootdiag_append "$v41_reason" || log 'V41_HEALTH_REASON_RECORD_FAILED'
        log "V41_HEALTH_FAILED reason=$v41_reason; POWER_OFF_REQUESTED"
        $BB poweroff -f
        /bin/boot-proof-reboot
        stop
    fi
fi
'''
sys.path.insert(0, str(PORT))
from image_formats import read_boot_v4, read_newc, require
from ramdisk_codec import decompress


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    os.umask(0o077)
    require(not OUT.exists(), 'Refuse to replace V41 candidate')
    parent = (BASE / 'nord3-delayed-health-v39-untested.img').read_bytes()
    require(sha(parent) == V39_SHA, 'V39 parent differs')
    boot = read_boot_v4(parent)
    primary = read_newc(decompress(boot['ramdisk']))
    old_init = primary['init']['data']
    require(old_init.count(MARKER) == 1, 'V39 init tail marker differs')
    tail = (PORT / 'lynx-v40-health-retry-tail.sh').read_bytes()
    require(tail.startswith(MARKER) and tail.count(OLD_SOURCE) == 1 and
            tail.count(FAIL_START) == 1 and tail.count(FAIL_END) == 1,
            'V40 tail source differs')
    before, remaining = tail.split(FAIL_START, 1)
    _, after = remaining.split(FAIL_END, 1)
    tail = (before + RETRY + FAIL_END + after).replace(b'V40_', b'V41_')
    init = old_init.split(MARKER)[0] + tail
    require(subprocess.run(['busybox', 'sh', '-n'], input=init,
                           capture_output=True).returncode == 0,
            'V41 init shell syntax failed')
    primary['init'] = {**primary['init'], 'data': init}
    ramdisk = stage.packed(primary)
    header = bytearray(parent[:1584])
    struct.pack_into('<I', header, 12, len(ramdisk))
    align = lambda size: (size + 4095) // 4096 * 4096
    loaded = (bytes(header).ljust(4096, b'\0') +
              boot['kernel'].ljust(align(len(boot['kernel'])), b'\0') +
              ramdisk.ljust(align(len(ramdisk)), b'\0'))
    recipe = json.loads((PORT / 'known-good-v19/recipe.json').read_text())
    coverage = recipe['coverage_bytes']
    require(len(loaded) <= coverage <= recipe['payload_offset'],
            'V41 primary overlaps supplement')
    image = loaded.ljust(coverage, b'\0') + parent[coverage:]
    require(len(image) == len(parent) == 67_108_864,
            'V41 image size differs')
    checked_boot = read_boot_v4(image)
    checked_primary = read_newc(decompress(checked_boot['ramdisk']))
    require(checked_boot['kernel'] == boot['kernel'] and
            checked_boot['cmdline'] == boot['cmdline'] and
            checked_primary == primary and image[coverage:] == parent[coverage:],
            'V41 roundtrip or unchanged supplement differs')
    OUT.mkdir(mode=0o700)
    target = OUT / 'nord3-health-primary-v41-untested.img'
    target.write_bytes(image)
    target.chmod(0o600)
    (OUT / 'init-source').write_bytes(init)
    result = {'state': 'offline-health-primary-built',
              'created_ns': time.time_ns(), 'parent_v39_sha256': V39_SHA,
              'image_sha256': sha(image), 'init_sha256': sha(init),
              'supplement_sha256': sha(parent[coverage:]),
              'supplement_unchanged': True,
              'stock_kernel_sha256': sha(boot['kernel']),
              'partition_scope_if_trialled': ['boot_a'],
              'phone_contacted': False, 'flash_performed': False,
              'diagnostic_question': 'Does a parent-only retry recover the V39 health refusal with the supplement unchanged?',
              'observation_limit_uptime_seconds': 300,
              'outer_poweroff_seconds_after_tail': 420}
    (OUT / 'build-result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'state': result['state'], 'result': str(OUT / 'build-result.json')}))


if __name__ == '__main__':
    main()
