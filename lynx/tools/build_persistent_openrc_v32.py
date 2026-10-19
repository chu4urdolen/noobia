"""Build a V29-derived Alpine handoff diagnostic with a primary-init-only edit.

V29's stock kernel and exact supplementary payload stay byte-for-byte intact.
PID 1 records the guard's stderr and retries only a clean guard refusal.
No phone contact or flash occurs here.
"""
import hashlib
import json
import os
from pathlib import Path
import stat
import struct
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
PORT = ROOT / 'linux-port'
BASE = PORT / 'artifacts/persistent-openrc-v29-offline'
OUT = PORT / 'artifacts/persistent-openrc-v32-offline'
sys.path.insert(0, str(PORT))
from image_formats import read_boot_v4, read_newc, require
from prepare_busybox_diagnostics import pack
from ramdisk_codec import decompress

V29_SHA = '2483ba8d5ee43ef2ba692885682b9ebacc59fdb8216700eaad1eff7c531b3048'
TAIL = b"""lynx_wifi_supervise || stop
log 'PINNED_SSH_CONFIRMED; PERSISTENT_OPENRC_WAIT'
. /etc/lynx/persistent-openrc-handoff.sh || { log 'PERSISTENT_OPENRC_SCRIPT_LOAD_FAILED'; stop; }
lynx_persistent_openrc_wait_and_handoff || log 'PERSISTENT_OPENRC_REFUSED; BUSYBOX_RESCUE_ACTIVE'
stop
"""
REPLACEMENT = b"""lynx_wifi_supervise || stop
log 'PINNED_SSH_CONFIRMED; PERSISTENT_OPENRC_WAIT'
. /etc/lynx/persistent-openrc-handoff.sh || { log 'PERSISTENT_OPENRC_SCRIPT_LOAD_FAILED'; stop; }
exec 2>>/run/lynx/openrc-pid1-stderr.log
openrc_attempt=1
while [ "$openrc_attempt" -le 3 ]; do
    log "PERSISTENT_OPENRC_ATTEMPT attempt=$openrc_attempt"
    lynx_persistent_openrc_wait_and_handoff && break
    openrc_last=$($BB tail -n 1 /run/lynx/boot.log) || break
    case "$openrc_last" in
        *PERSISTENT_OPENRC_SAFETY_GUARD_REFUSED) ;;
        *) break ;;
    esac
    [ ! -e /run/lynx/persistent-alpine ] || break
    [ "$openrc_attempt" -lt 3 ] || break
    log "PERSISTENT_OPENRC_GUARD_CLEAN_RETRY attempt=$openrc_attempt"
    $BB sleep 5
    openrc_attempt=$((openrc_attempt + 1))
done
log 'PERSISTENT_OPENRC_REFUSED; BUSYBOX_RESCUE_ACTIVE'
stop
"""


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    os.umask(0o077)
    require(not OUT.exists(), 'Refuse to overwrite V32 candidate')
    source = (BASE / 'nord3-persistent-openrc-untested.img').read_bytes()
    build = json.loads((BASE / 'build-result.json').read_text())
    require(sha(source) == V29_SHA == build['image_sha256'], 'V29 parent differs')
    recipe = json.loads((PORT / 'known-good-v19/recipe.json').read_text())
    offset = recipe['payload_offset']
    payload = (BASE / 'supplement.cpio.gz').read_bytes()
    require(source[offset:offset + len(payload)] == payload,
            'V29 supplement differs from embedded payload')
    boot = read_boot_v4(source)
    primary = read_newc(decompress(boot['ramdisk']))
    init = primary['init']['data']
    require(init.endswith(TAIL) and init.count(TAIL) == 1, 'V29 init tail differs')
    new_init = init[:-len(TAIL)] + REPLACEMENT
    primary['init'] = {**primary['init'], 'data': new_init}
    ramdisk = pack(dict(sorted(primary.items(), key=lambda pair: (
        not stat.S_ISDIR(pair[1]['mode']), pair[0].count('/'), pair[0]))))
    header = bytearray(source[:1584])
    struct.pack_into('<I', header, 12, len(ramdisk))
    align = lambda value: (value + 4095) // 4096 * 4096
    loaded = (bytes(header).ljust(4096, b'\0') +
              boot['kernel'].ljust(align(len(boot['kernel'])), b'\0') +
              ramdisk.ljust(align(len(ramdisk)), b'\0'))
    coverage = recipe['coverage_bytes']
    require(len(loaded) <= coverage <= offset, 'New primary overlaps payload')
    candidate = loaded.ljust(coverage, b'\0') + source[coverage:]
    require(len(candidate) == len(source) == 67_108_864, 'V32 image size differs')
    require(candidate[offset:] == source[offset:], 'V29 supplement/tail changed')
    checked = read_boot_v4(candidate)
    require(checked['kernel'] == boot['kernel'] and checked['cmdline'] == boot['cmdline'],
            'Kernel or cmdline changed')
    require(candidate[:12] == source[:12] and candidate[16:4096] == source[16:4096],
            'Boot header changed outside ramdisk length')
    checked_primary = read_newc(decompress(checked['ramdisk']))
    require(set(checked_primary) == set(primary), 'Primary member set changed')
    for name, entry in primary.items():
        require(checked_primary[name] == entry, 'Primary member roundtrip differs: ' + name)
    for name, entry in read_newc(decompress(boot['ramdisk'])).items():
        if name != 'init':
            require(checked_primary[name] == entry, 'Unrelated primary member changed: ' + name)
    OUT.mkdir(mode=0o700)
    image = OUT / 'nord3-persistent-openrc-v32-untested.img'
    image.write_bytes(candidate)
    image.chmod(0o600)
    (OUT / 'init-source').write_bytes(new_init)
    result = {'state': 'offline-primary-only-candidate-built',
              'created_ns': time.time_ns(), 'parent_v29_sha256': V29_SHA,
              'image_sha256': sha(candidate), 'image_bytes': len(candidate),
              'init_sha256': sha(new_init), 'supplement_sha256': sha(payload),
              'stock_kernel_sha256': sha(boot['kernel']),
              'changed_members': ['init'], 'phone_contacted': False,
              'flash_performed': False,
              'limitation': 'Offline validation only; a controlled boot_a trial and exact V19 rollback remain required.'}
    (OUT / 'build-result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'state': result['state'], 'result': str(OUT / 'build-result.json')}))


if __name__ == '__main__':
    main()
