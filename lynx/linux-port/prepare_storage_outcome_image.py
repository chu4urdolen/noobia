"""Offline storage-only outcome probe from the validated v4 image."""
import hashlib
import json
import secrets
import struct
from pathlib import Path
from image_formats import read_boot_v4, read_newc, require
from prepare_busybox_diagnostics import pack
from network_userspace import put
from ramdisk_codec import decompress

P = Path(__file__).resolve().parent
F = P / 'artifacts/busybox-wifi-ssh-twostage-v4'
OUT = P / 'artifacts/busybox-storage-outcome-v1'


def main():
    require(not OUT.exists(), 'Keep previous experiments immutable')
    image = (F / 'nord3-busybox-candidate.img').read_bytes()
    require(hashlib.sha256(image).hexdigest() == '0abe578cdc82a8f42b6bd812f3217dcc622f2a980d93e3c3418bc6dadf731af7', 'V4 changed')
    boot = read_boot_v4(image)
    first = read_newc(decompress(boot['ramdisk']))
    old_init = first['init']['data']
    marker = b"\nlog 'WIFI_TWO_STAGE_BOOTSTRAP_BEGIN'\n"
    require(old_init.count(marker) == 1, 'Probe prelude boundary changed')
    runtime = (P / 'lynx-storage-outcome-runtime.sh').read_bytes()
    init = old_init.split(marker)[0] + runtime + b"\nlog 'WIFI_TWO_STAGE_BOOTSTRAP_BEGIN'\nlynx_storage_probe\nstop\n"
    put(first, 'init', init)
    token = secrets.token_hex(16)
    put(first, 'etc/lynx/session-token', (token + '\n').encode(), 0o100644)
    ramdisk = pack(first)
    align = lambda n: (n + 4095) // 4096 * 4096
    header = bytearray(image[:1584])
    struct.pack_into('<I', header, 12, len(ramdisk))
    loaded = bytes(header).ljust(4096, b'\0') + boot['kernel'].ljust(align(len(boot['kernel'])), b'\0') + ramdisk.ljust(align(len(ramdisk)), b'\0')
    _, _, _, coverage, offset, size = struct.unpack('!4sIIQQQ28x', image[-64:])
    require(len(loaded) <= coverage, 'Probe exceeds preserved original loaded area')
    result = loaded.ljust(coverage, b'\0') + image[coverage:]
    require(len(result) == len(image) and result[coverage:] == image[coverage:], 'Outside loaded area changed')
    require(result[offset:offset + size] == image[offset:offset + size] and result[-64:] == image[-64:], 'Metadata/footer changed')
    require(read_boot_v4(result)['kernel'] == boot['kernel'], 'Kernel changed')
    OUT.mkdir(mode=0o700)
    for name, data in [('nord3-busybox-candidate.img', result), ('init-source', init)]:
        path = OUT / name
        path.write_bytes(data)
        path.chmod(0o600)
    previous = json.loads((F / 'build-validation.json').read_text())
    codes = {1: 'base module insertion failed', 2: 'storage module insertion failed',
             3: 'boot_a absent and no ufshcd-mtk driver binding seen',
             4: 'boot_a absent with ufshcd-mtk driver binding seen',
             5: 'own boot_a supplementary payload read/check/extraction failed',
             6: 'supplement verified and extracted successfully',
             7: 'bootstrap worker did not finish within180s', 8: 'other bootstrap failure'}
    report = {**previous, 'candidate': str(OUT / 'nord3-busybox-candidate.img'),
              'candidate_sha256': hashlib.sha256(result).hexdigest(), 'init_sha256': hashlib.sha256(init).hexdigest(),
              'ramdisk_bytes': len(ramdisk), 'session_token': token, 'network_trial': False,
              'runtime_sha256': hashlib.sha256(runtime).hexdigest(), 'result_codes': {str(k): v for k, v in codes.items()},
              'target_delays_seconds': {str(k): 40 + 25*k for k in codes},
              'baseline_reference_seconds': 21.624, 'timing_match_tolerance_seconds': 8,
              'flash_eligible': False, 'phone_contacted': False,
              'limits': ['One coarse result encoded by a single timed standard reboot; not a persistent hex log.',
                         'Classification is an inference requiring reset evidence and no physical interference.',
                         'Changed bootloader/kernel startup time or hardware stalls can invalidate timing classification.']}
    (OUT / 'build-validation.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: report[k] for k in ['candidate', 'candidate_sha256', 'ramdisk_bytes', 'target_delays_seconds']}, indent=2))


if __name__ == '__main__':
    main()
