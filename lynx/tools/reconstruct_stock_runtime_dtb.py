"""Apply the stock overlay selected in a saved LK log, entirely offline."""
import ctypes
import hashlib
import json
import re
import struct
from pathlib import Path
from audit_ufs_reset_supplier import fdt_nodes

ROOT = Path(__file__).resolve().parent.parent
P = ROOT / 'linux-port'
S = P / 'artifacts/stock-cph2493-August-eu-ota'


def main():
    log_path = ROOT / 'logs/pllk-1791796477741516715.clean.txt'
    indices = [int(n) for n in re.findall(r'find dynamic idx:(\d+)', log_path.read_text())]
    assert indices and set(indices) == {5}, indices
    wrapped = (S / 'unpacked-vendor-boot/dtb').read_bytes()
    start = wrapped.index(bytes.fromhex('d00dfeed'))
    size = struct.unpack_from('>I', wrapped, start + 4)[0]
    base = wrapped[start:start + size]
    table = (S / 'dtbo.img').read_bytes()
    magic, total, header_size, entry_size, count, entries, _, _ = struct.unpack_from('>8I', table)
    assert magic == 0xd7b7ab1e and total <= len(table) and header_size == 32 and entry_size == 32 and count > 5
    overlay_size, overlay_offset, identifier, revision, *custom = struct.unpack_from('>8I', table, entries + 5 * entry_size)
    assert overlay_offset + overlay_size <= total
    overlay = table[overlay_offset:overlay_offset + overlay_size]
    library_path = ROOT / 'tools/qemu/noble/root/usr/lib/x86_64-linux-gnu/libfdt-1.7.0.so'
    lib = ctypes.CDLL(str(library_path))
    lib.fdt_open_into.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int]
    lib.fdt_overlay_apply.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    lib.fdt_pack.argtypes = [ctypes.c_void_p]
    capacity = len(base) + len(overlay) + 1024 * 1024
    destination = ctypes.create_string_buffer(capacity)
    original = ctypes.create_string_buffer(base)
    layer = ctypes.create_string_buffer(overlay)
    assert lib.fdt_open_into(original, destination, capacity) == 0, 'FDT open failed'
    assert lib.fdt_overlay_apply(destination, layer) == 0, 'Stock overlay apply failed'
    assert lib.fdt_pack(destination) == 0, 'FDT pack failed'
    final_size = struct.unpack_from('>I', destination.raw, 4)[0]
    result = destination.raw[:final_size]
    nodes = fdt_nodes(result)
    out = P / 'artifacts/stock-runtime-dtb-overlay5'
    assert not out.exists(), 'Preserve existing reconstruction'
    out.mkdir()
    (out / 'stock-merged.dtb').write_bytes(result)
    properties = nodes['/ufshci@112b0000']
    report = {'phone_contacted': False, 'selected_index': 5, 'dtbo_id': identifier,
              'revision': revision, 'custom': custom, 'selection_log': str(log_path),
              'base_sha256': hashlib.sha256(base).hexdigest(), 'overlay_sha256': hashlib.sha256(overlay).hexdigest(),
              'merged_sha256': hashlib.sha256(result).hexdigest(), 'merged_bytes': len(result),
              'merged_dtb': str(out / 'stock-merged.dtb'),
              'libfdt_sha256': hashlib.sha256(library_path.read_bytes()).hexdigest(),
              'ufs_properties_hex': {k: v.hex() for k, v in properties.items()},
              'limits': 'Offline stock base+selected stock overlay; runtime bootloader fixups and dynamically inserted properties are not captured.'}
    (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'merged': str(out / 'stock-merged.dtb'), 'bytes': len(result),
                      'ufs_property_names': list(properties)}, indent=2))


if __name__ == '__main__':
    main()
