"""Build a RAM-only UFS matching guard diagnostic; never contact the phone."""
import hashlib
import json
import secrets
import struct
import sys
from pathlib import Path
from image_formats import read_boot_v4, read_newc, module_metadata, require
from ramdisk_codec import decompress
from network_userspace import put
from prepare_busybox_diagnostics import pack

P = Path(__file__).resolve().parent
sys.path.insert(0, str(P.parent / 'tools'))
from audit_ufs_reset_supplier import fdt_nodes
OUT = P / 'artifacts/busybox-ufs-registration-only-v1'
REF = P / 'artifacts/busybox-module-progress-debug-40-v1'
def sha(data): return hashlib.sha256(data).hexdigest()

def main():
    require(not OUT.exists(), 'Preserve existing candidate')
    original = (REF / 'nord3-busybox-candidate.img').read_bytes()
    require(sha(original) == '18a5250d0617c03a305381b6aa24e37a0f2681463e441f7771a586df4a2ec540', 'Reference changed')
    boot = read_boot_v4(original)
    entries = read_newc(decompress(boot['ramdisk']))
    old_runtime = (P / 'lynx-storage-prefix-progress-runtime.sh').read_bytes()
    suffix = old_runtime + b'\nlynx_module_progress\nstop\n'
    require(entries['init']['data'].endswith(suffix), 'Frozen init boundary changed')
    guard = (P / 'ufs-registration-guard.sh').read_bytes()
    runtime = (P / 'lynx-ufs-registration-runtime.sh').read_bytes()
    init = entries['init']['data'][:-len(suffix)] + guard + runtime + b'\nlynx_ufs_registration\nstop\n'
    put(entries, 'init', init)
    token = secrets.token_hex(16)
    put(entries, 'etc/lynx/session-token', (token + '\n').encode(), 0o100644)
    book = json.loads(entries['etc/lynx/diag-codebook.json']['data'])
    book['513'] = 'guarded UFS registration outcome'
    put(entries, 'etc/lynx/diag-codebook.json', (json.dumps(book, indent=2) + '\n').encode(), 0o100644)
    vendor = read_newc(decompress((P / 'artifacts/stock-cph2493-August-eu-ota/unpacked-vendor-boot/vendor_ramdisk00').read_bytes()))
    merged = {**vendor, **entries}
    module = merged['lib/modules/ufs-mediatek-mod.ko']['data']
    meta = module_metadata(module)['values']
    table = json.loads((P / 'docs/stock-ufs-match-table.json').read_text())
    require(table['module_sha256'] == sha(module) and table['exact_table_agrees_with_profile'], 'Exact OF table changed')
    require([r for r in table['table']['rows'] if r['compatible']] == [{'name':'', 'type':'', 'compatible':'mediatek,mt8183-ufshci'}], 'Additional matching targets need review')
    dtb = (P / 'artifacts/stock-runtime-dtb-overlay5/stock-merged.dtb').read_bytes()
    require(sha(dtb) == '802ba58739ece5e1dce26b98dff63b6f28b9f46695609439b7f4645d39e49319', 'Merged DT changed')
    nodes = fdt_nodes(dtb)
    require([n for n,p in nodes.items() if b'mediatek,mt8183-ufshci' in p.get('compatible',b'').split(b'\0')] == ['/ufshci@112b0000'], 'Unexpected UFS DT targets')
    rd = pack(entries)
    header = bytearray(original[:1584])
    struct.pack_into('<I', header, 12, len(rd))
    align = lambda n: (n + 4095) // 4096 * 4096
    loaded = bytes(header).ljust(4096, b'\0') + boot['kernel'].ljust(align(len(boot['kernel'])), b'\0') + rd.ljust(align(len(rd)), b'\0')
    coverage = struct.unpack('!4sIIQQQ28x', original[-64:])[3]
    require(len(loaded) <= coverage, 'Loaded image overlaps stock metadata')
    image = loaded.ljust(coverage, b'\0') + original[coverage:]
    OUT.mkdir(mode=0o700)
    for name, raw in [('nord3-busybox-candidate.img', image), ('init-source', init), ('guard-source', guard), ('runtime-source', runtime)]:
        path = OUT / name
        path.write_bytes(raw)
        path.chmod(0o600)
    report = dict(candidate_sha256=sha(image), reference_sha256=sha(original), kernel_sha256=sha(boot['kernel']), ramdisk_bytes=len(rd), guard_sha256=sha(guard), runtime_sha256=sha(runtime), init_sha256=sha(init), ufs_module_sha256=sha(module), ufs_module_metadata=meta, session_token=token, result_codes={'0':'guard verified and stock UFS insertion returned; hardware matching blocked','1':'guard refused','2':'UFS insertion failed','3':'worker still pending','4':'prefix insertion failed','5':'missing or malformed outcome'}, target_delays_seconds={str(i):120+5*i for i in range(6)}, worker_sample_seconds=90, observation_seconds=240, timing_match_tolerance_seconds=2, phone_contacted=False, flash_eligible=False)
    (OUT / 'build-validation.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))

if __name__ == '__main__': main()
