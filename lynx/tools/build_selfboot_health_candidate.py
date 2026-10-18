"""Build a private offline V25d BusyBox self-boot health prototype.

V25d starts health monitoring before Wi-Fi/SSH, without Nexus confirmation. It
does not hand over PID 1 to Alpine yet and must not be flashed while the
thermal safety hold remains active.
"""
import gzip
import json
import os
import struct
import sys
import time

import build_health_stage_candidate as stage

ROOT, PORT = stage.ROOT, stage.PORT
BASE = PORT / 'artifacts/health-stage-v23-offline'
OUT = PORT / 'artifacts/selfboot-health-v25d-offline'
sys.path.insert(0, str(PORT))
from image_formats import read_boot_v4, read_newc, require
from ramdisk_codec import decompress


OLD_TAIL = b''' . /etc/lynx/wifi-runtime.sh || stop
lynx_wifi_supervise || stop
log 'WIFI_SUPERVISOR_FINISHED; CHECKING_OPT_IN_OPENRC_GATE'
. /etc/lynx/openrc-handoff.sh || { log 'OPENRC_SCRIPT_LOAD_FAILED; REQUESTING_FASTBOOT'; /bin/boot-proof-reboot; stop; }
lynx_openrc_handoff
log 'OPENRC_HANDOFF_FAILED; REQUESTING_FASTBOOT'
/bin/boot-proof-reboot
stop
'''.lstrip()

NEW_TAIL = b'''log 'LOCAL_BOOTSTRAP_READY; PREPARING_GUARDED_HEALTH'
local_token=$($BB cat /etc/lynx/session-token) || stop
[ -n "$local_token" ] || stop
printf '%s\n' "$local_token" > /run/lynx/local-boot-ready.tmp || stop
$BB mv /run/lynx/local-boot-ready.tmp /run/lynx/local-boot-ready || stop
. /etc/lynx/autonomous-health-local-handoff.sh || { log 'LOCAL_HEALTH_SCRIPT_LOAD_FAILED'; $BB poweroff -f; /bin/boot-proof-reboot; stop; }
lynx_autonomous_health_local_handoff || { log 'LOCAL_HEALTH_BOOT_FAILED; POWER_OFF_REQUESTED'; $BB poweroff -f; /bin/boot-proof-reboot; stop; }
log 'LOCAL_HEALTH_ACTIVE; STARTING_WIFI'
. /etc/lynx/wifi-runtime.sh || { log 'LOCAL_WIFI_SCRIPT_LOAD_FAILED'; /bin/boot-proof-reboot; stop; }
. /etc/lynx/wifi-local-supervise.sh || { log 'LOCAL_WIFI_SUPERVISOR_LOAD_FAILED'; /bin/boot-proof-reboot; stop; }
lynx_wifi_supervise_local || stop
log 'LOCAL_SELFBOOT_WIFI_SSH_HEALTH_ACTIVE; BUSYBOX_PID1_RESCUE_READY'
stop
'''.lstrip()


def main(out=OUT, new_tail=NEW_TAIL, variant='V25d'):
    os.umask(0o077)
    require(not out.exists(), 'Refuse to replace ' + variant + ' prototype')
    parent = json.loads((BASE / 'build-result.json').read_text())
    source = (BASE / 'nord3-health-stage-inert.img').read_bytes()
    require(parent.get('state') == 'offline-inert-health-stage-packaged' and
            stage.sha(source) == parent['image_sha256'] ==
            'c2cc903904255d7cdac00a9dd3cd60c7fde75cfe21e2dc331afafb02eb24e402',
            'V23 source differs')
    boot = read_boot_v4(source)
    primary = read_newc(decompress(boot['ramdisk']))
    old_primary = {name: dict(entry) for name, entry in primary.items()}
    old_init = primary['init']['data']
    require(old_init.endswith(OLD_TAIL) and old_init.count(OLD_TAIL) == 1,
            'V23 init handoff site differs')
    new_init = old_init[:-len(OLD_TAIL)] + new_tail
    primary['init'] = {**primary['init'], 'data': new_init}

    recipe = json.loads((PORT / 'known-good-v19/recipe.json').read_text())
    offset = recipe['payload_offset']
    old_payload = source[offset:]
    old_length = parent['supplement_bytes']
    require(stage.sha(old_payload[:old_length]) == parent['supplement_sha256'],
            'V23 supplement differs')
    supplement = read_newc(gzip.decompress(old_payload[:old_length]))
    old_supplement = {name: dict(entry) for name, entry in supplement.items()}
    replacements = {
        'usr/libexec/lynx/autonomous-health-start.sh':
            PORT / 'autonomous-health-start.sh',
    }
    additions = {
        'etc/lynx/wifi-local-supervise.sh':
            PORT / 'lynx-wifi-local-supervise.sh',
        'etc/lynx/autonomous-health-local-handoff.sh':
            PORT / 'autonomous-health-local-handoff.sh',
    }
    for name, path in replacements.items():
        require(name in supplement, 'Expected V23 health script absent: ' + name)
        data = path.read_bytes()
        require(data.startswith(b'#!/bin/sh\n'), 'Replacement interpreter differs: ' + name)
        supplement[name] = {**supplement[name], 'data': data}
    for name, path in additions.items():
        data = path.read_bytes()
        require(data.startswith(b'#!/bin/sh\n'), 'Added interpreter differs: ' + name)
        stage.put(supplement, name, data, 0o700)
    new_payload = gzip.compress(decompress(stage.packed(supplement)), compresslevel=9, mtime=0)
    require(len(new_payload) < 40_000_000, 'V25 payload exceeds loader bound')
    primary['etc/lynx/payload-bytes'] = {
        **primary['etc/lynx/payload-bytes'], 'data': (str(len(new_payload)) + '\n').encode()}
    primary['etc/lynx/payload-sha256'] = {
        **primary['etc/lynx/payload-sha256'], 'data': (stage.sha(new_payload) + '\n').encode()}
    ramdisk = stage.packed(primary)
    header = bytearray(source[:1584])
    struct.pack_into('<I', header, 12, len(ramdisk))
    align = lambda value: (value + 4095) // 4096 * 4096
    loaded = (bytes(header).ljust(4096, b'\0') +
              boot['kernel'].ljust(align(len(boot['kernel'])), b'\0') +
              ramdisk.ljust(align(len(ramdisk)), b'\0'))
    coverage = recipe['coverage_bytes']
    require(len(loaded) <= coverage <= offset and
            offset + len(new_payload) < len(source) - 4096,
            'V25c overlaps boot-image boundaries')
    image = bytearray(loaded.ljust(coverage, b'\0') + source[coverage:])
    image[offset:offset + max(len(new_payload), old_length)] = new_payload.ljust(
        max(len(new_payload), old_length), b'\0')
    image = bytes(image)
    require(len(image) == 67_108_864 and read_boot_v4(image)['kernel'] == boot['kernel'],
            'V25c kernel, header or image size differs')
    require(image[:12] == source[:12] and image[16:4096] == source[16:4096] and
            read_boot_v4(image)['cmdline'] == boot['cmdline'],
            'V25c boot header changed outside ramdisk length')
    checked_primary = read_newc(decompress(read_boot_v4(image)['ramdisk']))
    require(checked_primary['init']['data'] == new_init and
            checked_primary['etc/lynx/payload-sha256']['data'].strip().decode() == stage.sha(new_payload),
            'V25c init or payload metadata round trip differs')
    require(set(checked_primary) == set(old_primary), 'V25c primary member set differs')
    for name, entry in old_primary.items():
        if name not in ('init', 'etc/lynx/payload-bytes', 'etc/lynx/payload-sha256'):
            require(checked_primary[name] == entry, 'V25c changed unrelated primary member: ' + name)
    checked_supplement = read_newc(gzip.decompress(image[offset:offset + len(new_payload)]))
    require(set(checked_supplement) == set(old_supplement) | set(additions),
            'V25c supplement member set differs')
    for name, entry in old_supplement.items():
        if name not in replacements:
            require(checked_supplement[name] == entry,
                    'V25c changed unrelated supplement member: ' + name)
    for name, path in {**replacements, **additions}.items():
        require(checked_supplement[name]['data'] == path.read_bytes(),
                'V25c script differs after packing: ' + name)
    require(checked_supplement['usr/share/lynx/health-inputs.tar.gz'] ==
            old_supplement['usr/share/lynx/health-inputs.tar.gz'],
            'V25c changed reviewed module archive')

    out.mkdir(mode=0o700)
    target = out / 'nord3-selfboot-health-untested.img'
    target.write_bytes(image)
    target.chmod(0o600)
    result = {
        'state': 'offline-selfboot-health-candidate-untested', 'variant': variant,
        'created_ns': time.time_ns(), 'image_sha256': stage.sha(image),
        'image_bytes': len(image), 'parent_v23_sha256': stage.sha(source),
        'stock_kernel_sha256': stage.sha(boot['kernel']),
        'old_init_sha256': stage.sha(old_init), 'new_init_sha256': stage.sha(new_init),
        'payload_sha256': stage.sha(new_payload), 'payload_bytes': len(new_payload),
        'script_sha256': {name: stage.sha(path.read_bytes()) for name, path in
                          {**replacements, **additions}.items()},
        'phone_contacted': False, 'flash_performed': False,
        'inherits_private_v19_wifi_and_ssh_credentials': True, 'image_mode': '0600',
        'limits': 'Offline image layout only. Self-boot control and failure paths have not run on Lynx. No Alpine PID 1 or persistent rootfs. SAFETY-HOLD remains active; DO NOT FLASH.'}
    (out / 'build-result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'state': result['state'], 'image_sha256': result['image_sha256'],
                      'result': str(out / 'build-result.json')}))


if __name__ == '__main__':
    main()
