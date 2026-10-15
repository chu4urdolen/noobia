"""Offline full-module checkpoint with only the MTU3 null guard substituted."""
import hashlib
import json
from pathlib import Path
import struct
from image_formats import read_boot_v4, read_newc, require
from ramdisk_codec import decompress
from prepare_busybox_diagnostics import pack

BASE = Path(__file__).resolve().parent
OUTPUT = BASE / 'artifacts/busybox-mtu3-null-guard-checkpoint'


def main():
    require(not OUTPUT.exists(), 'Preserve existing guard image')
    source = (BASE / 'artifacts/busybox-usb-module-checkpoints/with-mtu3/nord3-busybox-candidate.img').read_bytes()
    require(hashlib.sha256(source).hexdigest() == '5bb984899b19c9e739faa23aa9039374a5ad20ab99c10948d5d2b964da3616d6', 'Full checkpoint changed')
    module = (BASE / 'artifacts/mtu3-null-child-guard/mtu3.ko').read_bytes()
    require(hashlib.sha256(module).hexdigest() == '49688170d2be04c5051331f93ddf8eda8d8bc5ce37baf82dd04d2edb7f657223', 'Guarded module changed')
    boot = read_boot_v4(source)
    original = read_newc(decompress(boot['ramdisk']))
    entries = {name: dict(item) for name, item in original.items()}
    path = 'lib/modules/mtu3.ko'
    require(hashlib.sha256(entries[path]['data']).hexdigest() == 'd3c59fa794a6e02f014dd0de660592bb66c9d7f8eb941c1d1183f8a3322bb467', 'Original generic module differs')
    entries[path]['data'] = module
    require([name for name in original if original[name] != entries[name]] == [path], 'Unrelated archive change')
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
    (OUTPUT / 'init-source').write_bytes(entries['init']['data'])
    (OUTPUT / 'build-validation.json').write_text(json.dumps(dict(candidate_sha256=hashlib.sha256(image).hexdigest(), module_sha256=hashlib.sha256(module).hexdigest(), only_changed_archive_entry=path, init_kernel_module_order_identical=True, phone_contacted=False, flash_eligible=False, hardware_fix_proven=False, limits='Offline controlled checkpoint only. No gadget/role calls added. Corrects one conditional pointer construction; actual hardware failure cause remains unproved.'), indent=2) + '\n')
    print('Guard checkpoint SHA256:', hashlib.sha256(image).hexdigest())


if __name__ == '__main__':
    main()
