"""Prepare a stock-module supervisor diagnostic offline, never flash."""
import hashlib
import json
from pathlib import Path
import struct
from image_formats import read_boot_v4, read_newc, require
from ramdisk_codec import decompress
from prepare_busybox_diagnostics import pack

BASE = Path(__file__).resolve().parent
OUTPUT = BASE / 'artifacts/busybox-mtu3-timed-supervisor'


def main():
    require(not OUTPUT.exists(), 'Preserve previous supervisor image')
    source = (BASE / 'artifacts/busybox-usb-module-checkpoints/with-mtu3/nord3-busybox-candidate.img').read_bytes()
    require(hashlib.sha256(source).hexdigest() == '5bb984899b19c9e739faa23aa9039374a5ad20ab99c10948d5d2b964da3616d6', 'Full checkpoint changed')
    boot = read_boot_v4(source)
    original = read_newc(decompress(boot['ramdisk']))
    entries = {name: dict(item) for name, item in original.items()}
    full = original['etc/lynx-checkpoint-modules.load']['data'].decode().splitlines()
    require(len(full) == 34 and full[-1] == 'mtu3.ko', 'Module boundary changed')
    entries['etc/lynx-checkpoint-modules.load']['data'] = ('\n'.join(full[:-1]) + '\n').encode()
    init = original['init']['data']
    marker = b'log "CHECKPOINT_ALL_MODULES_LOADED; REQUESTING_ONE_RESTART2_BOOTLOADER"'
    require(init.count(marker) == 1, 'Footer changed')
    supervisor = (BASE / 'mtu3-timed-supervisor.sh').read_bytes()
    init = init[:init.index(marker)] + supervisor + b"\nlynx_mtu3_supervise || log 'SUPERVISOR_REFUSED_OR_FAILED'\nstop\n"
    require(init.count(b'/bin/boot-proof-reboot\n') == 1, 'Expected one parent reset call')
    require(hashlib.sha256(entries['lib/modules/mtu3.ko']['data']).hexdigest() == 'd3c59fa794a6e02f014dd0de660592bb66c9d7f8eb941c1d1183f8a3322bb467', 'Expected original stock MTU3')
    entries['init']['data'] = init
    require([name for name in original if original[name] != entries[name]] == ['init', 'etc/lynx-checkpoint-modules.load'], 'Unrelated changes')
    ramdisk = pack(entries)
    header = bytearray(source[:1584])
    struct.pack_into('<I', header, 12, len(ramdisk))
    align = lambda size: (size + 4095) // 4096 * 4096
    payload = bytes(header).ljust(4096, b'\0') + boot['kernel'].ljust(align(len(boot['kernel'])), b'\0') + ramdisk.ljust(align(len(ramdisk)), b'\0')
    magic, _, _, coverage, offset, _ = struct.unpack('!4sIIQQQ28x', source[-64:])
    require(magic == b'AVBf' and len(payload) <= coverage <= offset, 'Metadata overlap')
    image = payload.ljust(coverage, b'\0') + source[coverage:]
    require(len(image) == 67108864 and read_boot_v4(image)['kernel'] == boot['kernel'], 'Kernel/geometry changed')
    require(read_newc(decompress(read_boot_v4(image)['ramdisk'])) == entries, 'Final archive differs')
    OUTPUT.mkdir()
    (OUTPUT / 'nord3-busybox-candidate.img').write_bytes(image)
    (OUTPUT / 'init-source').write_bytes(init)
    (OUTPUT / 'build-validation.json').write_text(json.dumps(dict(candidate_sha256=hashlib.sha256(image).hexdigest(), supervisor_source_sha256=hashlib.sha256(supervisor).hexdigest(), changed_archive_entries=['init', 'etc/lynx-checkpoint-modules.load'], all_modules_original_stock=True, clock='integer seconds from proc uptime', observation_seconds=15, child_relative_reboot_deadlines=dict(success=20, error=40, no_result_within_15_seconds=60), phone_contacted=False, flash_eligible=False, limits='Timing beacon only if parent scheduling and kernel reboot remain viable. Infer timing with calibration and input/reset controls; kernel fault or shutdown lock may prevent return.'), indent=2) + '\n')
    print('Supervisor candidate SHA256:', hashlib.sha256(image).hexdigest())


if __name__ == '__main__':
    main()
