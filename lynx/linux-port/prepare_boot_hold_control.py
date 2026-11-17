"""Matching minimal boot control with the native reboot request removed; offline."""
import hashlib
import json
from pathlib import Path
import struct
from image_formats import read_boot_v4, read_newc, require
from ramdisk_codec import decompress
from prepare_busybox_diagnostics import pack

BASE = Path(__file__).resolve().parent
OUTPUT = BASE / 'artifacts/busybox-minimal-hold-control'


def main():
    require(not OUTPUT.exists(), 'Preserve existing control image')
    source = BASE / 'artifacts/busybox-August-boot-proof-bound-guards/nord3-busybox-candidate.img'
    data = source.read_bytes()
    require(hashlib.sha256(data).hexdigest() == 'a9a72334185a5ddec9b6e3ece6e9e01600582f62c4db7bebc8ce87c4d5c3fe43', 'Proven reference changed')
    boot = read_boot_v4(data)
    original = read_newc(decompress(boot['ramdisk']))
    entries = {name: dict(item) for name, item in original.items()}
    before = b"    log 'BOUND_STOCK_DRIVERS; REQUESTING_ONE_RESTART2_BOOTLOADER'\n    /bin/boot-proof-reboot\n    log 'REBOOT_SYSCALL_RETURNED; NO_RETRY'"
    after = b"    log 'BOUND_STOCK_DRIVERS; HOLD_CONTROL_NO_REBOOT_REQUEST'"
    require(entries['init']['data'].count(before) == 1, 'Expected source block changed')
    entries['init']['data'] = entries['init']['data'].replace(before, after)
    require(b'/bin/boot-proof-reboot' not in entries['init']['data'], 'Control still requests reboot')
    # Retain even the unused helper: the sole archive-content difference is init.
    require([name for name in original if original[name] != entries[name]] == ['init'], 'Unrelated archive modification')
    ramdisk = pack(entries)
    header = bytearray(data[:1584])
    struct.pack_into('<I', header, 12, len(ramdisk))
    align = lambda size: (size + 4095) // 4096 * 4096
    payload = bytes(header).ljust(4096, b'\0') + boot['kernel'].ljust(align(len(boot['kernel'])), b'\0') + ramdisk.ljust(align(len(ramdisk)), b'\0')
    magic, _, _, coverage, offset, _ = struct.unpack('!4sIIQQQ28x', data[-64:])
    require(magic == b'AVBf' and len(payload) <= coverage <= offset, 'Metadata overlap')
    image = payload.ljust(coverage, b'\0') + data[coverage:]
    require(len(image) == len(data) == 67108864, 'Partition size changed')
    require(read_boot_v4(image)['kernel'] == boot['kernel'], 'Kernel changed')
    require(read_newc(decompress(read_boot_v4(image)['ramdisk'])) == entries, 'Final archive differs')
    OUTPUT.mkdir()
    (OUTPUT / 'nord3-busybox-candidate.img').write_bytes(image)
    (OUTPUT / 'init-source').write_bytes(entries['init']['data'])
    (OUTPUT / 'initramfs.cpio.lz4').write_bytes(ramdisk)
    report = dict(candidate_sha256=hashlib.sha256(image).hexdigest(), reference_sha256=hashlib.sha256(data).hexdigest(),
                  only_changed_archive_entry='init', reboot_request_removed=True, helper_retained_unused=True,
                  kernel_identical=True, phone_contacted=False, hardware_tested=False, flash_eligible=False,
                  limits='Offline control only. No direct output channel. A hold requires physical return to Fastboot. Both images still have intentionally mismatching modified-data hashes; not OEM signed.')
    (OUTPUT / 'build-validation.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
