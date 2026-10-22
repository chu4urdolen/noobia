"""Build a bounded, offline V44 local Alpine handoff probe from proven V43."""
import gzip
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
BASE = PORT / 'artifacts/health-tolerance-v43-offline'
OUT = PORT / 'artifacts/local-openrc-probe-v44-offline'
V43_SHA = '4c088d2b4aca070510291322b9a809947100cecf0909bc458727914f5afbd875'
V43_INIT_SHA = 'ce0df400f2a013fca1edf47602d05bd1ccfe373e5225e7fa102b4e1be3f425f4'
HELPER_SHA = 'efa8fa664943902301358df80a948f289690d2714995ee94d89be612083ca5b3'
MARKER = b"log 'V41_HEALTH_READY; BUSYBOX_PID1_OBSERVATION_WINDOW'\n"
OLD_STAGES = b'|HEALTH_READY|CHARGER_ON|END)'
NEW_STAGES = b'|HEALTH_READY|HANDOFF_BEGIN|HANDOFF_REFUSED|CHARGER_ON|END)'
sys.path.insert(0, str(PORT))
from image_formats import read_boot_v4, read_newc, require
from ramdisk_codec import decompress


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    os.umask(0o077)
    require(not OUT.exists(), 'Refuse to replace V44 candidate')
    parent = (BASE / 'nord3-health-tolerance-v43-untested.img').read_bytes()
    require(sha(parent) == V43_SHA, 'V43 parent differs')
    boot = read_boot_v4(parent)
    primary = read_newc(decompress(boot['ramdisk']))
    old_init = primary['init']['data']
    require(sha(old_init) == V43_INIT_SHA and old_init.count(MARKER) == 1 and
            old_init.count(OLD_STAGES) == 1, 'V43 init differs')
    tail = (PORT / 'lynx-v44-local-openrc-tail.sh').read_bytes()
    require(tail.startswith(b"log 'V44_HEALTH_READY;") and
            tail.endswith(b'/bin/boot-proof-reboot\nstop\n'),
            'V44 tail bounds differ')
    untrimmed = old_init.split(MARKER)[0].replace(OLD_STAGES, NEW_STAGES) + tail
    # The AVB-covered ramdisk has only 22 compressed bytes free. Remove only
    # full-line shell comments; no executable line or string is rewritten.
    lines = untrimmed.splitlines(keepends=True)
    removed = [line for line in lines if line.startswith(b'#') and
               not line.startswith(b'#!')]
    require(len(removed) == 12 and all(line.endswith(b'\n') for line in removed),
            'Unexpected V43 comment inventory')
    init = b''.join(line for line in lines if line not in removed)
    require(subprocess.run(['busybox', 'sh', '-n'], input=init,
                           capture_output=True).returncode == 0,
            'V44 init shell syntax failed')
    recipe = json.loads((PORT / 'known-good-v19/recipe.json').read_text())
    coverage, offset = recipe['coverage_bytes'], recipe['payload_offset']
    payload_bytes = int(primary['etc/lynx/payload-bytes']['data'])
    payload = parent[offset:offset + payload_bytes]
    require(sha(payload) == primary['etc/lynx/payload-sha256']['data'].decode().strip(),
            'V43 supplement hash differs')
    supplement = read_newc(gzip.decompress(payload))
    helper = supplement['etc/lynx/persistent-openrc-handoff.sh']['data']
    require(sha(helper) == HELPER_SHA and
            helper == (PORT / 'persistent-openrc-handoff-v34.sh').read_bytes() and
            b'LYNX_OPENRC_AUTHORITY=local' in helper,
            'Local authority handoff helper differs')
    primary['init'] = {**primary['init'], 'data': init}
    ramdisk = stage.packed(primary)
    header = bytearray(parent[:1584])
    struct.pack_into('<I', header, 12, len(ramdisk))
    align = lambda value: (value + 4095) // 4096 * 4096
    loaded = (bytes(header).ljust(4096, b'\0') +
              boot['kernel'].ljust(align(len(boot['kernel'])), b'\0') +
              ramdisk.ljust(align(len(ramdisk)), b'\0'))
    require(len(loaded) <= coverage <= offset,
            f'V44 primary exceeds AVB-covered region by {len(loaded)-coverage} bytes')
    image = loaded.ljust(coverage, b'\0') + parent[coverage:]
    require(len(image) == len(parent) == 67_108_864,
            'V44 image size differs')
    checked = read_boot_v4(image)
    require(checked['kernel'] == boot['kernel'] and
            checked['cmdline'] == boot['cmdline'] and
            read_newc(decompress(checked['ramdisk'])) == primary and
            image[coverage:] == parent[coverage:],
            'V44 changed unrelated scope or failed roundtrip')
    OUT.mkdir(mode=0o700)
    target = OUT / 'nord3-local-openrc-probe-v44-untested.img'
    target.write_bytes(image)
    target.chmod(0o600)
    (OUT / 'init-source').write_bytes(init)
    result = {'state': 'offline-local-openrc-probe-built',
              'created_ns': time.time_ns(), 'parent_v43_sha256': V43_SHA,
              'image_sha256': sha(image), 'init_sha256': sha(init),
              'stock_kernel_sha256': sha(boot['kernel']),
              'supplement_sha256': sha(parent[coverage:]),
              'local_handoff_helper_sha256': HELPER_SHA,
              'primary_changes': ['init'], 'supplement_unchanged': True,
              'removed_comment_lines': len(removed),
              'partition_scope_if_trialled': ['boot_a'],
              'phone_contacted': False, 'flash_performed': False,
              'diagnostic_question': 'After three passing health checks, can Lynx hand off to Alpine/OpenRC without host arming?',
              'outer_poweroff_seconds_after_tail': 420,
              'bounded_trial': True}
    (OUT / 'build-result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'state': result['state'],
                      'result': str(OUT / 'build-result.json')}))


if __name__ == '__main__':
    main()
