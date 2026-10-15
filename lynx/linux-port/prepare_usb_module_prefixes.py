"""Offline dependency-checked prefixes of the failed full module checkpoint."""
import hashlib
import json
from pathlib import Path
import struct
from image_formats import read_boot_v4, read_newc, require
from ramdisk_codec import decompress
from prepare_busybox_diagnostics import pack

BASE = Path(__file__).resolve().parent
SOURCE = BASE / 'artifacts/busybox-usb-module-checkpoints/with-mtu3'
OUTPUT = BASE / 'artifacts/busybox-usb-module-prefixes'
STOCK = BASE / 'artifacts/stock-cph2493-August-eu-ota'


def main():
    require(not OUTPUT.exists(), 'Preserve existing prefixes')
    data = (SOURCE / 'nord3-busybox-candidate.img').read_bytes()
    require(hashlib.sha256(data).hexdigest() == '5bb984899b19c9e739faa23aa9039374a5ad20ab99c10948d5d2b964da3616d6', 'Full checkpoint changed')
    boot = read_boot_v4(data)
    original = read_newc(decompress(boot['ramdisk']))
    names = original['etc/lynx-checkpoint-modules.load']['data'].decode().splitlines()
    require(len(names) == 34, 'Unexpected module count')
    deps = {}
    for line in (STOCK / 'vendor-ramdisk-unpacked/lib/modules/modules.dep').read_text().splitlines():
        name, _, values = line.partition(':')
        deps[Path(name).name] = [Path(value).name for value in values.split()]
    OUTPUT.mkdir()
    results = []
    for count in [5, 17, 26]:
        selected = names[:count]
        loaded = {'mtk_wdt.ko', 'reboot-mode.ko', 'syscon-reboot-mode.ko'}
        for name in selected:
            require(name in deps, 'Module missing from dependency file')
            require(set(deps[name]) <= loaded, 'Forward/missing module dependency: ' + name)
            loaded.add(name)
        entries = {name: dict(item) for name, item in original.items()}
        entries['etc/lynx-checkpoint-modules.load']['data'] = ('\n'.join(selected) + '\n').encode()
        require([name for name in original if original[name] != entries[name]] == ['etc/lynx-checkpoint-modules.load'], 'Unexpected archive change')
        ramdisk = pack(entries)
        header = bytearray(data[:1584])
        struct.pack_into('<I', header, 12, len(ramdisk))
        align = lambda size: (size + 4095) // 4096 * 4096
        payload = bytes(header).ljust(4096, b'\0') + boot['kernel'].ljust(align(len(boot['kernel'])), b'\0') + ramdisk.ljust(align(len(ramdisk)), b'\0')
        magic, _, _, coverage, offset, _ = struct.unpack('!4sIIQQQ28x', data[-64:])
        require(magic == b'AVBf' and len(payload) <= coverage <= offset, 'Metadata overlap')
        image = payload.ljust(coverage, b'\0') + data[coverage:]
        require(len(image) == 67108864, 'Image geometry changed')
        require(read_newc(decompress(read_boot_v4(image)['ramdisk'])) == entries, 'Final archive mismatch')
        folder = OUTPUT / str(count)
        folder.mkdir()
        (folder / 'nord3-busybox-candidate.img').write_bytes(image)
        (folder / 'init-source').write_bytes(entries['init']['data'])
        report = dict(prefix_count=count, total_modules_including_reset=count + 3, additional_modules=selected,
                      candidate_sha256=hashlib.sha256(image).hexdigest(), init_identical_to_full_checkpoint=True,
                      only_changed_archive_entry='etc/lynx-checkpoint-modules.load', module_dependency_order_checked=True,
                      phone_contacted=False, flash_eligible=False, hardware_tested=False,
                      limits='A return supports successful insertion of this prefix; absence does not identify which insertion or guard/reset step failed.')
        (folder / 'build-validation.json').write_text(json.dumps(report, indent=2) + '\n')
        results.append(report)
    (OUTPUT / 'summary.json').write_text(json.dumps(results, indent=2) + '\n')
    print(json.dumps([dict(prefix=r['prefix_count'], sha256=r['candidate_sha256']) for r in results], indent=2))


if __name__ == '__main__':
    main()
