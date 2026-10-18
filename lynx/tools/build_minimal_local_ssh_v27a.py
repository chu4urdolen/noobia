"""Build a minimal autonomous Wi-Fi diagnostic from exact working V19.

Only /init, Wi-Fi supervisor, and payload metadata change. A 180-second RAM
timer powers off the phone even after SSH succeeds. Offline build only.
"""
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
SOURCE = PORT / 'artifacts/busybox-wifi-ssh-twostage-v19/nord3-busybox-candidate.img'
OUT = PORT / 'artifacts/minimal-local-ssh-v27a-offline'
SOURCE_SHA = '5ce2dbf8a7c132fa7e31f6be70aa76f83afe8c293e2cd5f02251a532486fd851'
sys.path.insert(0, str(PORT))
from image_formats import read_boot_v4, read_newc, require
from ramdisk_codec import decompress

OLD_TAIL = b'''. /etc/lynx/wifi-runtime.sh || stop
lynx_wifi_supervise
log 'WIFI_SUPERVISOR_FINISHED; PID1_REMAINS_ALIVE'
stop
'''
NEW_TAIL = rb'''. /etc/lynx/wifi-runtime.sh || stop
( $BB sleep 180; log 'MINIMAL_LOCAL_SSH_DEADLINE_POWER_OFF'; $BB poweroff -f ) > /run/lynx/local-ssh-timer.log 2>&1 < /dev/null &
printf '%s\n' "$!" > /run/lynx/local-ssh-timer.pid
lynx_wifi_supervise
log 'MINIMAL_LOCAL_SSH_RETURNED; PID1_REMAINS_ALIVE_UNTIL_TIMER'
stop
'''
OLD_WIFI = rb'''        if [ -f /run/lynx/ssh-ready ]; then
            # Only public discovery metadata leaves the phone before SSH.
            printf 'LYNX_HELLO %s\n' "$token" | /usr/bin/nc -u -w 1 "$host" 5514
        fi
'''
NEW_WIFI = rb'''        if [ -f /run/lynx/ssh-ready ]; then
            # Emit the proven V19 beacon before accepting local SSH readiness.
            for local_beacon in 1 2 3; do
                printf 'LYNX_HELLO %s\n' "$token" | /usr/bin/nc -u -w 1 "$host" 5514 || true
                $BB sleep 1
            done
            if [ -r /run/lynx/ssh.pid ] && [ -r /run/lynx/address ] &&
                    [ -r /run/lynx/interface ]; then
                IFS= read -r local_pid < /run/lynx/ssh.pid || return 1
                IFS= read -r local_address < /run/lynx/address || return 1
                IFS= read -r local_interface < /run/lynx/interface || return 1
                case "$local_pid" in ''|*[!0-9]*) return 1;; esac
                case "$local_address" in ''|*[!0-9.]*) return 1;; esac
                case "$local_interface" in wlan0|wlan1) ;; *) return 1;; esac
                if [ -d "/sys/class/net/$local_interface" ] &&
                        kill -0 "$local_pid" 2>/dev/null; then
                    log "MINIMAL_LOCAL_SSH_READY interface=$local_interface address=$local_address"
                    return 0
                fi
            fi
        fi
'''


def main():
    os.umask(0o077)
    require(not OUT.exists(), 'Refuse to replace V27a prototype')
    source = SOURCE.read_bytes()
    require(stage.sha(source) == SOURCE_SHA and len(source) == 67108864,
            'Working V19 source differs')
    recipe = json.loads((PORT / 'known-good-v19/recipe.json').read_text())
    offset = recipe['payload_offset']
    boot = read_boot_v4(source)
    primary = read_newc(decompress(boot['ramdisk']))
    old_primary = {name: dict(entry) for name, entry in primary.items()}
    old_init = primary['init']['data']
    require(old_init.endswith(OLD_TAIL) and old_init.count(OLD_TAIL) == 1,
            'V19 init tail differs')
    new_init = old_init[:-len(OLD_TAIL)] + NEW_TAIL
    require(subprocess.run(['sh', '-n'], input=new_init, capture_output=True).returncode == 0,
            'Modified init shell syntax failed')
    primary['init'] = {**primary['init'], 'data': new_init}
    old_length = int(primary['etc/lynx/payload-bytes']['data'])
    old_payload = source[offset:offset + old_length]
    require(stage.sha(old_payload) == primary['etc/lynx/payload-sha256']['data'].strip().decode(),
            'V19 supplement differs')
    supplement = read_newc(gzip.decompress(old_payload))
    old_supplement = {name: dict(entry) for name, entry in supplement.items()}
    member = 'etc/lynx/wifi-runtime.sh'
    old_wifi = supplement[member]['data']
    require(old_wifi.count(OLD_WIFI) == 1, 'V19 Wi-Fi supervisor site differs')
    new_wifi = old_wifi.replace(OLD_WIFI, NEW_WIFI)
    require(subprocess.run(['sh', '-n'], input=new_wifi, capture_output=True).returncode == 0,
            'Modified Wi-Fi runtime shell syntax failed')
    supplement[member] = {**supplement[member], 'data': new_wifi}
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
            'V27a overlaps boot image boundaries')
    image = bytearray(loaded.ljust(recipe['coverage_bytes'], b'\0') +
                      source[recipe['coverage_bytes']:])
    image[offset:offset + max(old_length, len(new_payload))] = new_payload.ljust(
        max(old_length, len(new_payload)), b'\0')
    image = bytes(image)
    checked_boot = read_boot_v4(image)
    require(len(image) == len(source) and checked_boot['kernel'] == boot['kernel'] and
            checked_boot['cmdline'] == boot['cmdline'] and image[:12] == source[:12] and
            image[16:4096] == source[16:4096], 'V27a kernel/header changed')
    checked_primary = read_newc(decompress(checked_boot['ramdisk']))
    require(set(checked_primary) == set(old_primary) and
            checked_primary['init']['data'] == new_init, 'V27a init round trip differs')
    for name, entry in old_primary.items():
        if name not in ('init', 'etc/lynx/payload-bytes', 'etc/lynx/payload-sha256'):
            require(checked_primary[name] == entry,
                    'V27a changed unrelated primary member: ' + name)
    checked_supplement = read_newc(gzip.decompress(image[offset:offset + len(new_payload)]))
    require(set(checked_supplement) == set(old_supplement),
            'V27a changed supplement member set')
    for name, entry in old_supplement.items():
        require(checked_supplement[name] == (supplement[name] if name == member else entry),
                'V27a changed unrelated supplement member: ' + name)
    OUT.mkdir(mode=0o700)
    target = OUT / 'nord3-minimal-local-ssh-untested.img'
    target.write_bytes(image)
    target.chmod(0o600)
    result = {
        'state': 'offline-minimal-local-ssh-untested', 'variant': 'V27a',
        'created_ns': time.time_ns(), 'image_sha256': stage.sha(image),
        'image_bytes': len(image), 'parent_v19_sha256': SOURCE_SHA,
        'stock_kernel_sha256': stage.sha(checked_boot['kernel']),
        'init_sha256': stage.sha(new_init),
        'payload_sha256': stage.sha(new_payload), 'payload_bytes': len(new_payload),
        'changed_supplement_member': member, 'wifi_runtime_sha256': stage.sha(new_wifi),
        'phone_contacted': False, 'flash_performed': False,
        'image_mode': '0600',
        'limits': 'Offline diagnostic only. No automatic health; 180-second timer powers off. Do not flash under general hold without scoped review.'}
    (OUT / 'build-result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'state': result['state'], 'image_sha256': result['image_sha256'],
                      'payload_bytes': len(new_payload),
                      'result': str(OUT / 'build-result.json')}))


if __name__ == '__main__':
    main()
