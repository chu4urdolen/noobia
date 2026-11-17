#!/usr/bin/env python3
"""Make a one-instruction, offline Nord 3 panel cold-init module candidate."""

import hashlib
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parent.parent
STOCK = ROOT / "linux-port/artifacts/stock-cph2493-August-eu-ota/vendor-ramdisk-unpacked/lib/modules/oplus22823_tm_nt37705_fhd_dsi_cmd.ko"
STOCK_SHA = "498be900a01f21eba3116820d4fae965ee3796a953d30f66fb4aa72436334e98"
SOURCE = ROOT / "linux-port/sources/oneplus-mt6983-kernel-13.1"
SOURCE_COMMIT = "81ec42ad5e803be0cba619f9f7bb298db7d33d7b"
SOURCE_PATH = "drivers/gpu/drm/panel/oplus22823_tm_nt37705_fhd_dsi_cmd.c"
OUT = ROOT / "linux-port/artifacts/panel-cold-init-v50-offline"
MODULE = OUT / "oplus22823_tm_nt37705_fhd_dsi_cmd-cold-init.ko"
TEXT_FILE_OFFSET = 0x1000
PATCH_TEXT_OFFSET = 0x121C
PATCH_FILE_OFFSET = TEXT_FILE_OFFSET + PATCH_TEXT_OFFSET
ORIGINAL = bytes.fromhex("28 20 80 52")  # mov w8,#257
REPLACEMENT = bytes.fromhex("08 00 80 52")  # mov w8,#0
KERNEL = "5.10.149-android12-9-o-g311738fbb5a8"


def run(*argv, cwd=None):
    return subprocess.run(argv, cwd=cwd, check=True, capture_output=True,
                          text=True).stdout


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    stock = STOCK.read_bytes()
    if hashlib.sha256(stock).hexdigest() != STOCK_SHA:
        raise RuntimeError("matching August stock panel module hash changed")
    if run("git", "rev-parse", "HEAD", cwd=SOURCE).strip() != SOURCE_COMMIT:
        raise RuntimeError("Nord 3 kernel source checkout changed")
    source = run("git", "show", "HEAD:" + SOURCE_PATH, cwd=SOURCE)
    probe = source.split("static int lcm_probe(", 1)[1].split("static int lcm_remove(", 1)[0]
    if "ctx->prepared = true;" not in probe or "ctx->enabled = true;" not in probe:
        raise RuntimeError("stock source no longer initializes both flags true")
    sections = run("readelf", "-W", "-S", str(STOCK))
    if not any(".text" in line and "001000 006ca0" in line for line in sections.splitlines()):
        raise RuntimeError("stock ELF text section layout changed")
    symbols = run("readelf", "-W", "-s", str(STOCK))
    if "0000000000000f70  1280 FUNC" not in symbols or " lcm_probe" not in symbols:
        raise RuntimeError("lcm_probe symbol layout changed")
    relocations = run("readelf", "-W", "-r", str(STOCK))
    if any(line.startswith("000000000000121c ") for line in relocations.splitlines()):
        raise RuntimeError("patch instruction has relocation")
    if stock[PATCH_FILE_OFFSET:PATCH_FILE_OFFSET + 4] != ORIGINAL:
        raise RuntimeError("the stock instruction is not mov w8,#257")
    if stock[PATCH_FILE_OFFSET + 0x14:PATCH_FILE_OFFSET + 0x18] != bytes.fromhex("68 22 01 79"):
        raise RuntimeError("paired strh to panel flags changed")
    if not run("modinfo", "-F", "vermagic", str(STOCK)).startswith(KERNEL + " "):
        raise RuntimeError("stock module kernel ABI mismatch")

    candidate = bytearray(stock)
    candidate[PATCH_FILE_OFFSET:PATCH_FILE_OFFSET + 4] = REPLACEMENT
    MODULE.write_bytes(candidate)
    diffs = [i for i, (a, b) in enumerate(zip(stock, candidate)) if a != b]
    if diffs != [PATCH_FILE_OFFSET, PATCH_FILE_OFFSET + 1]:
        raise RuntimeError(f"unexpected changed byte offsets: {diffs}")
    if run("modinfo", "-F", "vermagic", str(MODULE)) != run("modinfo", "-F", "vermagic", str(STOCK)):
        raise RuntimeError("candidate module ABI metadata changed")
    if run("modinfo", "-F", "depends", str(MODULE)) != run("modinfo", "-F", "depends", str(STOCK)):
        raise RuntimeError("candidate dependency metadata changed")
    if run("readelf", "-W", "-s", str(MODULE)) != symbols:
        raise RuntimeError("candidate symbol table changed")
    if run("readelf", "-W", "-r", str(MODULE)) != relocations:
        raise RuntimeError("candidate relocation table changed")
    report = {
        "state": "offline-validated-not-loaded",
        "source_commit": SOURCE_COMMIT,
        "source_path": SOURCE_PATH,
        "stock_module": str(STOCK),
        "stock_sha256": STOCK_SHA,
        "candidate_module": str(MODULE),
        "candidate_sha256": hashlib.sha256(candidate).hexdigest(),
        "patch_file_offset_hex": hex(PATCH_FILE_OFFSET),
        "patch_text_offset_hex": hex(PATCH_TEXT_OFFSET),
        "stock_instruction": ORIGINAL.hex(),
        "candidate_instruction": REPLACEMENT.hex(),
        "changed_byte_offsets_hex": [hex(x) for x in diffs],
        "boot_partition_writes": False,
        "phone_writes": False,
        "note": "ELF build-id remains stock; identify candidate by SHA-256, not build-id",
    }
    (OUT / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"state": report["state"],
                      "candidate_sha256": report["candidate_sha256"],
                      "manifest": str(OUT / 'manifest.json')}))


if __name__ == "__main__":
    main()
