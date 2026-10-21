"""Independently validate V39 delayed-health scope and rollback inputs."""
import hashlib
import gzip
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
PORT = ROOT / 'linux-port'
OUT = PORT / 'artifacts/delayed-health-v39-offline'
V38 = PORT / 'artifacts/persistent-trace-v38-offline/nord3-persistent-trace-v38-untested.img'
V33 = PORT / 'artifacts/persistent-openrc-v33-offline/nord3-persistent-openrc-v33-untested.img'
V19 = PORT / 'artifacts/busybox-wifi-ssh-twostage-v19/nord3-busybox-candidate.img'
STOCK = PORT / 'artifacts/stock-cph2493-August-eu-ota'
MODEL = ROOT / 'tools/avb-host/avb-boot-model'
MARKER = b'. /etc/lynx/wifi-runtime.sh || stop\n. /etc/lynx/wifi-local-supervise.sh || stop\n'
sys.path.insert(0, str(PORT))
from image_formats import read_boot_v4, read_newc
from ramdisk_codec import decompress


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def run(argv, *, data=None, timeout=30):
    result = subprocess.run(argv, input=data, capture_output=True, timeout=timeout)
    if result.returncode:
        raise ValueError('Validation failed: ' + str(argv) + ' ' +
                         result.stderr[-300:].decode(errors='replace'))
    return result.stdout


def main():
    build = json.loads((OUT / 'build-result.json').read_text())
    image = OUT / 'nord3-delayed-health-v39-untested.img'
    candidate, parent, v33, v19, stock = (path.read_bytes() for path in
        (image, V38, V33, V19, STOCK / 'boot.img'))
    if (build['state'] != 'offline-delayed-health-diagnostic-built' or
            sha(candidate) != build['image_sha256'] or
            sha(parent) != build['parent_v38_sha256'] ==
            'ba1176676174bef30d111bff51139f238117f89e416b7fa72c2619f53396b8ad' or
            sha(v33) != '1d65456979d8a48d31de77c987b8aaf9b5ac11af62c51d00fdaff68ad47e747f' or
            sha(v19) != '5ce2dbf8a7c132fa7e31f6be70aa76f83afe8c293e2cd5f02251a532486fd851'):
        raise ValueError('Candidate, parent or rollback image differs')
    boot, base, stock_boot = map(read_boot_v4, (candidate, parent, stock))
    if (boot['kernel'] != base['kernel'] or boot['kernel'] != stock_boot['kernel'] or
            boot['cmdline'] != base['cmdline']):
        raise ValueError('Kernel or cmdline differs')
    entries = read_newc(decompress(boot['ramdisk']))
    old = read_newc(decompress(base['ramdisk']))
    if (set(entries) != set(old) or
            any(entries[name] != old[name] for name in old if name != 'init')):
        raise ValueError('Changes extend beyond primary init')
    tail = (PORT / 'lynx-v39-delayed-health-tail.sh').read_bytes()
    init = entries['init']['data']
    if (old['init']['data'].count(MARKER) != 1 or
            init != old['init']['data'].split(MARKER)[0] + tail or
            not tail.startswith(MARKER) or
            b'V39_WIFI_READY; HEALTH_DELAYED_UNTIL_UPTIME_190' not in tail or
            b'V39_OBSERVATION_COMPLETE; POWER_OFF_REQUESTED' not in tail or
            b'lynx_autonomous_health_local_handoff || {' not in tail or
            b'lynx_persistent_openrc_handoff' in tail or
            b'HEALTH_BEGIN' not in tail or b'HEALTH_READY' not in tail or
            b'[ "$v39_uptime" -lt 190 ] || break' not in tail or
            b'[ "$v39_uptime" -lt 300 ] || break' not in tail or
            b'$BB sleep 420' not in tail):
        raise ValueError('V39 bounded diagnostic tail differs')
    for required in (
            b"$BB grep -Fx 'PARTNAME=userdata' /sys/class/block/sdc85/uevent",
            b'[ "$($BB cat /sys/class/block/sdc85/size)" = 466026432 ]',
            b'UUID="13dc3665-b062-405e-b674-ceae8972fc0f"',
            b"TYPE=\"ext4\"",
            b'! $BB grep -Eq',
            b'$BB mount -t ext4 -o rw,nosuid,nodev,noexec /dev/sdc85',
            b'$BB sync -f "$diag_file"',
            b'$BB umount "$diag_root"',
            b'LXBD1 %s %s %s',
            b'UPTIME_120', b'UPTIME_150', b'UPTIME_180',
            b'V39_CHARGER_GUARD_POWER_OFF',
            b'$BB sh /run/lynx/lynx-health-supervisor.sh --once'):
        if required not in tail:
            raise ValueError('V39 persistent log or health guard differs: ' + repr(required))
    run(['busybox', 'sh', '-n'], data=init)
    recipe = json.loads((PORT / 'known-good-v19/recipe.json').read_text())
    if candidate[recipe['coverage_bytes']:] != parent[recipe['coverage_bytes']:]:
        raise ValueError('Supplement, AVB footer or trailing bytes differ')
    payload_bytes = int(entries['etc/lynx/payload-bytes']['data'])
    payload_offset = recipe['payload_offset']
    payload = candidate[payload_offset:payload_offset + payload_bytes]
    if sha(payload) != entries['etc/lynx/payload-sha256']['data'].decode().strip():
        raise ValueError('Supplement hash differs from primary metadata')
    supplement = read_newc(gzip.decompress(payload))
    for member, source in (
            ('usr/libexec/lynx/autonomous-health-start.sh',
             PORT / 'autonomous-health-start-v31.sh'),
            ('etc/lynx/autonomous-health-local-handoff.sh',
             PORT / 'autonomous-health-local-handoff.sh')):
        if supplement[member]['data'] != source.read_bytes():
            raise ValueError('Packaged health script differs: ' + member)
    reference = json.loads((PORT / 'docs/avb-boot-model-results.json').read_text())
    if sha(MODEL.read_bytes()) != reference['binary_sha256']:
        raise ValueError('AVB model differs')
    avb = [json.loads(run([str(MODEL), str(STOCK), str(image), '0', str(unlocked)]))
           for unlocked in (1, 0)]
    if (not avb[0]['slot_data_returned'] or avb[0]['boot_partitions_loaded'] != 1 or
            avb[1]['slot_data_returned'] or avb[1]['boot_partitions_loaded'] != 0):
        raise ValueError('AVB model behavior differs')
    result = {'state': 'offline-v39-validation-passed',
              'created_ns': time.time_ns(), 'image_sha256': sha(candidate),
              'stock_kernel_sha256': sha(boot['kernel']),
              'init_only_change_from_v38': True, 'supplement_unchanged': True,
              'rollback_v33_sha256': sha(v33), 'rollback_v19_sha256': sha(v19),
              'avb_cases': avb, 'phone_contacted': False,
              'flash_performed': False,
              'limit': 'Offline validation does not prove health-module behavior, ext4 mount/write safety, Wi-Fi persistence, or power-off on Lynx.'}
    (OUT / 'validation.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'state': result['state'],
                      'result': str(OUT / 'validation.json')}))


if __name__ == '__main__':
    main()
