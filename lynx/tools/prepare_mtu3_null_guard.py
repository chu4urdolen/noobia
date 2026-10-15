"""Offline, fixed-stock MTU3 guard for NULL child driver; no phone operations."""
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parent.parent
PROJECT = ROOT / 'linux-port'
sys.path.insert(0, str(PROJECT))
from image_formats import require, module_metadata


def main():
    folder = PROJECT / 'artifacts/mtu3-null-child-guard'
    require(not folder.exists(), 'Preserve previous guard artifacts')
    stock = PROJECT / 'artifacts/stock-cph2493-August-eu-ota/vendor-ramdisk-unpacked/lib/modules/mtu3.ko'
    data = stock.read_bytes()
    audit = json.loads((PROJECT / 'docs/august-vendor-ramdisk-audit.json').read_text())
    expected = next(item['sha256'] for item in audit['entries'] if item['path'] == 'lib/modules/mtu3.ko')
    require(hashlib.sha256(data).hexdigest() == expected, 'Stock module changed')
    require(data[:6] == b'\x7fELF\x02\x01' and struct.unpack_from('<H', data, 18)[0] == 183, 'Expected ELF64 ARM64')
    shoff = struct.unpack_from('<Q', data, 40)[0]
    shsize, count, name_index = struct.unpack_from('<HHH', data, 58)
    require(shsize == 64, 'Unexpected ELF section size')
    sections = [struct.unpack_from('<IIQQQQIIQQ', data, shoff + n * shsize) for n in range(count)]
    name_table = data[sections[name_index][4]:sections[name_index][4] + sections[name_index][5]]
    names = [name_table[section[0]:].split(b'\0', 1)[0].decode() for section in sections]
    text_index = names.index('.text')
    text = sections[text_index]
    start = text[4] + 0x54d0
    before = [0xaa0003e8, 0xf9404d08, 0x2a1f03e0]
    after = [0xf9404c08, 0x2a1f03e0, 0xb4000068]
    require(list(struct.unpack_from('<III', data, start)) == before, 'Target instructions differ')
    require(list(struct.unpack_from('<III', data, start + 12)) == [0xd100a108, 0xf900be68, 0x17ffffb6], 'Target continuation differs')
    for section in sections:
        if section[1] != 4 or section[7] != text_index:
            continue
        require(section[9] == 24, 'Unexpected RELA size')
        for offset in range(section[4], section[4] + section[5], 24):
            location = struct.unpack_from('<Q', data, offset)[0]
            require(not 0x54d0 <= location < 0x54dc, 'Relocation overlaps guard')
    modified = bytearray(data)
    struct.pack_into('<III', modified, start, *after)
    require(modified[:start] == data[:start] and modified[start + 12:] == data[start + 12:], 'Unrelated bytes changed')
    require(module_metadata(bytes(modified)) == module_metadata(data), 'Module metadata changed')
    folder.mkdir()
    (folder / 'mtu3.ko').write_bytes(modified)
    report = dict(stock_file=str(stock), stock_sha256=expected, modified_sha256=hashlib.sha256(modified).hexdigest(),
                  file_offset=start, text_offset='0x54d0', changed_region_bytes=12,
                  before_words=[hex(word) for word in before], after_words=[hex(word) for word in after],
                  intent='Load child driver directly from x0, preserve zero return, skip container conversion/storage when the driver is NULL.',
                  branch_target='0x54e4 existing branch to stack-cleanup/return',
                  module_metadata_identical=True, relocation_overlap=False, other_bytes_identical=True,
                  original_elf_build_id_retained=True, phone_contacted=False, flash_eligible=False,
                  hardware_fault_cause_proven=False,
                  limits='Offline experimental guard only. ELF build-id is retained and no longer describes unchanged code; use SHA256 and this manifest. Imported symbol versions/CFI-related sections remain byte-identical. Requires independent instruction and behavior validation before trial.')
    (folder / 'manifest.json').write_text(json.dumps(report, indent=2) + '\n')
    (folder / 'source-equivalent.patch').write_text('''--- a/drivers/usb/mtu3/mtu3_host.c
+++ b/drivers/usb/mtu3/mtu3_host.c
@@ -272,7 +272,9 @@ static void ssusb_get_platform_driver(struct ssusb_mtk *ssusb)
         if (of_device_is_compatible(child, "mediatek,mtk-xhci") ||
             of_device_is_compatible(child, "mediatek,mtk-xhci-p1")) {
             pdev = of_find_device_by_node(child);
-            if (pdev) {
+            if (pdev) {
+                if (!pdev->dev.driver)
+                    break;
                 ssusb->xhci_pdrv =
                     to_platform_driver(pdev->dev.driver);
                 break;
''')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
