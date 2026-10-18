"""Build an offline local-health candidate from proven autonomous V27a."""
import gzip
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import time

import build_health_stage_candidate as stage

ROOT, PORT = stage.ROOT, stage.PORT
SOURCE = PORT / 'artifacts/minimal-local-ssh-v27a-offline/nord3-minimal-local-ssh-untested.img'
OUT = PORT / 'artifacts/local-health-v28-offline'
SOURCE_SHA = 'db5381f525153971bc878109e67f47ad3256d6454d69eeab0802e3477e0024f4'
sys.path.insert(0, str(PORT))
from image_formats import read_boot_v4, read_newc, require
from ramdisk_codec import decompress

OLD_TAIL = rb'''. /etc/lynx/wifi-runtime.sh || stop
( $BB sleep 180; log 'MINIMAL_LOCAL_SSH_DEADLINE_POWER_OFF'; $BB poweroff -f ) > /run/lynx/local-ssh-timer.log 2>&1 < /dev/null &
printf '%s\n' "$!" > /run/lynx/local-ssh-timer.pid
lynx_wifi_supervise
log 'MINIMAL_LOCAL_SSH_RETURNED; PID1_REMAINS_ALIVE_UNTIL_TIMER'
stop
'''
NEW_TAIL = rb'''. /etc/lynx/wifi-runtime.sh || stop
( $BB sleep 300; log 'LOCAL_HEALTH_OUTER_DEADLINE_POWER_OFF'; $BB poweroff -f ) > /run/lynx/local-health-timer.log 2>&1 < /dev/null &
outer_timer=$!
printf '%s\n' "$outer_timer" > /run/lynx/local-health-timer.pid
lynx_wifi_supervise || { log 'LOCAL_WIFI_FAILED; POWER_OFF_REQUESTED'; $BB poweroff -f; stop; }
log 'LOCAL_WIFI_READY; STARTING_AUTONOMOUS_HEALTH'
local_token=$($BB cat /etc/lynx/session-token) || stop
[ -n "$local_token" ] || stop
printf '%s\n' "$local_token" > /run/lynx/local-boot-ready.tmp || stop
$BB mv /run/lynx/local-boot-ready.tmp /run/lynx/local-boot-ready || stop
. /etc/lynx/autonomous-health-local-handoff.sh || { log 'LOCAL_HEALTH_SCRIPT_LOAD_FAILED'; $BB poweroff -f; stop; }
lynx_autonomous_health_local_handoff || { log 'LOCAL_HEALTH_FAILED; POWER_OFF_REQUESTED'; $BB poweroff -f; stop; }
[ -f /run/lynx/health-bootstrap/ready ] || { log 'LOCAL_HEALTH_READY_MARKER_MISSING'; $BB poweroff -f; stop; }
kill "$outer_timer" || { log 'LOCAL_HEALTH_OUTER_TIMER_CANCEL_FAILED'; $BB poweroff -f; stop; }
wait "$outer_timer" 2>/dev/null || true
log 'LOCAL_WIFI_SSH_AND_HEALTH_READY; BUSYBOX_PID1'
stop
'''


def main():
    os.umask(0o077)
    require(not OUT.exists(), 'Refuse to replace V28 prototype')
    source = SOURCE.read_bytes()
    require(stage.sha(source) == SOURCE_SHA and len(source) == 67108864,
            'Proven V27a source differs')
    recipe = json.loads((PORT / 'known-good-v19/recipe.json').read_text())
    offset = recipe['payload_offset']
    boot = read_boot_v4(source)
    primary = read_newc(decompress(boot['ramdisk']))
    old_primary = {name: dict(entry) for name, entry in primary.items()}
    old_init = primary['init']['data']
    require(old_init.endswith(OLD_TAIL) and old_init.count(OLD_TAIL) == 1,
            'V27a init tail differs')
    new_init = old_init[:-len(OLD_TAIL)] + NEW_TAIL
    require(subprocess.run(['sh', '-n'], input=new_init, capture_output=True).returncode == 0,
            'Modified init shell syntax failed')
    primary['init'] = {**primary['init'], 'data': new_init}
    old_length = int(primary['etc/lynx/payload-bytes']['data'])
    old_payload = source[offset:offset + old_length]
    require(stage.sha(old_payload) == primary['etc/lynx/payload-sha256']['data'].strip().decode(),
            'V27a supplement differs')
    supplement = read_newc(gzip.decompress(old_payload))
    old_supplement = {name: dict(entry) for name, entry in supplement.items()}
    health_source = PORT / 'artifacts/health-stage-v23-offline/nord3-health-stage-inert.img'
    health_report = json.loads((health_source.parent / 'build-result.json').read_text())
    health_bytes = health_source.read_bytes()
    require(stage.sha(health_bytes) == health_report['image_sha256'] ==
            'c2cc903904255d7cdac00a9dd3cd60c7fde75cfe21e2dc331afafb02eb24e402',
            'Reviewed V23 health input source differs')
    health_primary = read_newc(decompress(read_boot_v4(health_bytes)['ramdisk']))
    health_length = int(health_primary['etc/lynx/payload-bytes']['data'])
    health_supplement = read_newc(gzip.decompress(health_bytes[offset:offset + health_length]))
    additions = ['usr/libexec', 'usr/share', 'usr/libexec/lynx', 'usr/share/lynx',
                 'usr/libexec/lynx/autonomous-health-preflight.sh',
                 'usr/share/lynx/health-inputs.sha256',
                 'usr/share/lynx/health-inputs.tar.gz']
    for name in additions:
        require(name not in supplement and name in health_supplement,
                'Health input member missing or collides: ' + name)
        supplement[name] = dict(health_supplement[name])
    start_member = 'usr/libexec/lynx/autonomous-health-start.sh'
    start_bytes = (PORT / 'autonomous-health-start.sh').read_bytes()
    require(start_member not in supplement and
            subprocess.run(['sh', '-n'], input=start_bytes, capture_output=True).returncode == 0,
            'Current health start script differs or fails syntax')
    supplement[start_member] = {**health_supplement[start_member], 'data': start_bytes}
    handoff_member = 'etc/lynx/autonomous-health-local-handoff.sh'
    handoff_bytes = (PORT / 'autonomous-health-local-handoff.sh').read_bytes()
    require(handoff_member not in supplement and
            subprocess.run(['sh', '-n'], input=handoff_bytes, capture_output=True).returncode == 0,
            'Local health handoff differs or fails syntax')
    stage.put(supplement, handoff_member, handoff_bytes, 0o700)
    new_payload = gzip.compress(decompress(stage.packed(supplement)),
                                compresslevel=9, mtime=0)
    require(len(new_payload) < 40_000_000, 'Payload exceeds V19 loader bound')
    primary['etc/lynx/payload-bytes'] = {
        **primary['etc/lynx/payload-bytes'],
        'data': (str(len(new_payload)) + '\n').encode()}
    primary['etc/lynx/payload-sha256'] = {
        **primary['etc/lynx/payload-sha256'],
        'data': (stage.sha(new_payload) + '\n').encode()}
    ramdisk = stage.packed(primary)
    header = bytearray(source[:1584])
    struct.pack_into('<I', header, 12, len(ramdisk))
    align = lambda n: (n + 4095) // 4096 * 4096
    loaded = (bytes(header).ljust(4096, b'\0') +
              boot['kernel'].ljust(align(len(boot['kernel'])), b'\0') +
              ramdisk.ljust(align(len(ramdisk)), b'\0'))
    require(len(loaded) <= recipe['coverage_bytes'] <= offset and
            offset + max(old_length, len(new_payload)) < len(source) - 4096,
            'V28 overlaps boot image boundaries')
    image = bytearray(loaded.ljust(recipe['coverage_bytes'], b'\0') +
                      source[recipe['coverage_bytes']:])
    image[offset:offset + max(old_length, len(new_payload))] = new_payload.ljust(
        max(old_length, len(new_payload)), b'\0')
    image = bytes(image)
    checked_boot = read_boot_v4(image)
    require(len(image) == len(source) and checked_boot['kernel'] == boot['kernel'] and
            checked_boot['cmdline'] == boot['cmdline'] and image[:12] == source[:12] and
            image[16:4096] == source[16:4096], 'V28 kernel/header changed')
    checked_primary = read_newc(decompress(checked_boot['ramdisk']))
    require(set(checked_primary) == set(old_primary) and
            checked_primary['init']['data'] == new_init, 'V28 init round trip differs')
    for name, entry in old_primary.items():
        if name not in ('init', 'etc/lynx/payload-bytes', 'etc/lynx/payload-sha256'):
            require(checked_primary[name] == entry,
                    'V28 changed unrelated primary member: ' + name)
    checked_supplement = read_newc(gzip.decompress(image[offset:offset + len(new_payload)]))
    require(set(checked_supplement) == set(old_supplement) | set(additions) |
            {start_member, handoff_member}, 'V28 changed supplement member set')
    for name, entry in old_supplement.items():
        require(checked_supplement[name] == entry,
                'V28 changed unrelated supplement member: ' + name)
    for name in additions + [start_member, handoff_member]:
        require(checked_supplement[name] == supplement[name],
                'V28 health member round trip differs: ' + name)
    OUT.mkdir(mode=0o700)
    target = OUT / 'nord3-local-health-untested.img'
    target.write_bytes(image)
    target.chmod(0o600)
    result = {
        'state': 'offline-local-health-untested', 'variant': 'V28',
        'created_ns': time.time_ns(), 'image_sha256': stage.sha(image),
        'image_bytes': len(image), 'parent_v27a_sha256': SOURCE_SHA,
        'stock_kernel_sha256': stage.sha(checked_boot['kernel']),
        'init_sha256': stage.sha(new_init),
        'payload_sha256': stage.sha(new_payload), 'payload_bytes': len(new_payload),
        'health_input_members': additions + [start_member, handoff_member],
        'health_start_sha256': stage.sha(start_bytes),
        'local_handoff_sha256': stage.sha(handoff_bytes),
        'phone_contacted': False, 'flash_performed': False,
        'image_mode': '0600',
        'limits': 'Offline candidate only. Automatic health startup and timer cancellation are untested on Lynx; charging remains unvalidated. Do not flash under general hold without scoped review.'}
    (OUT / 'build-result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'state': result['state'], 'image_sha256': result['image_sha256'],
                      'payload_bytes': len(new_payload),
                      'result': str(OUT / 'build-result.json')}))


if __name__ == '__main__':
    main()
