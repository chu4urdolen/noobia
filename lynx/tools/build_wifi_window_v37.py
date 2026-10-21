"""Build a bounded Wi-Fi-only V37 diagnostic from exact V36, offline."""
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import time

import build_health_stage_candidate as stage

ROOT, PORT = stage.ROOT, stage.PORT
BASE = PORT / 'artifacts/local-cooldown-v36-offline'
OUT = PORT / 'artifacts/wifi-only-window-v37-offline'
V36_SHA = '75bbd8b44d728a1264f55ce3aff521400d25ea6b3e900c8bacca757cdfe49a50'
MARKER = b'. /etc/lynx/wifi-runtime.sh || stop\n. /etc/lynx/wifi-local-supervise.sh || stop\n'
sys.path.insert(0, str(PORT))
from image_formats import read_boot_v4, read_newc, require
from ramdisk_codec import decompress


def main():
    os.umask(0o077)
    require(not OUT.exists(), 'Refuse to replace V37 offline candidate')
    parent = (BASE / 'nord3-local-cooldown-v36-untested.img').read_bytes()
    require(stage.sha(parent) == V36_SHA, 'V36 parent differs')
    recipe = json.loads((PORT / 'known-good-v19/recipe.json').read_text())
    coverage, offset = recipe['coverage_bytes'], recipe['payload_offset']
    boot = read_boot_v4(parent)
    entries = read_newc(decompress(boot['ramdisk']))
    old_init = entries['init']['data']
    require(old_init.count(MARKER) == 1, 'V36 init tail marker differs')
    tail = (PORT / 'lynx-v37-wifi-window-tail.sh').read_bytes()
    require(tail.startswith(MARKER), 'V37 tail marker differs')
    new_init = old_init.split(MARKER)[0] + tail
    require(subprocess.run(['busybox', 'sh', '-n'], input=new_init,
                           capture_output=True).returncode == 0,
            'V37 init shell syntax failed')
    entries['init'] = {**entries['init'], 'data': new_init}
    ramdisk = stage.packed(entries)
    header = bytearray(parent[:1584])
    struct.pack_into('<I', header, 12, len(ramdisk))
    align = lambda value: (value + 4095) // 4096 * 4096
    loaded = (bytes(header).ljust(4096, b'\0') +
              boot['kernel'].ljust(align(len(boot['kernel'])), b'\0') +
              ramdisk.ljust(align(len(ramdisk)), b'\0'))
    require(len(loaded) <= coverage <= offset, 'V37 boot overlaps supplement')
    image = loaded.ljust(coverage, b'\0') + parent[coverage:]
    require(len(image) == len(parent) == 67_108_864,
            'V37 image size differs')
    checked_boot = read_boot_v4(image)
    checked_entries = read_newc(decompress(checked_boot['ramdisk']))
    require(checked_boot['kernel'] == boot['kernel'] and
            checked_boot['cmdline'] == boot['cmdline'] and
            set(checked_entries) == set(entries) and
            all(checked_entries[name] == entries[name] for name in entries) and
            image[coverage:] == parent[coverage:],
            'V37 changed unrelated image bytes or failed roundtrip')
    OUT.mkdir(mode=0o700)
    target = OUT / 'nord3-wifi-only-window-v37-untested.img'
    target.write_bytes(image)
    target.chmod(0o600)
    (OUT / 'init-source').write_bytes(new_init)
    result = {'state': 'offline-wifi-only-diagnostic-built',
              'created_ns': time.time_ns(), 'parent_v36_sha256': V36_SHA,
              'image_sha256': stage.sha(image), 'init_sha256': stage.sha(new_init),
              'stock_kernel_sha256': stage.sha(boot['kernel']),
              'supplement_unchanged': True,
              'partition_scope_if_trialled': ['boot_a'],
              'phone_contacted': False, 'flash_performed': False,
              'diagnostic_question': 'Does pinned Wi-Fi SSH survive to uptime 190 seconds without starting V31 health?',
              'observation_limit_uptime_seconds': 190,
              'outer_poweroff_seconds_after_tail': 230}
    (OUT / 'build-result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'state': result['state'],
                      'result': str(OUT / 'build-result.json')}))


if __name__ == '__main__':
    main()
