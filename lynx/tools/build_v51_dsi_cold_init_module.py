#!/usr/bin/env python3
"""Build an offline DSI module candidate that skips the LK display handoff."""

import hashlib
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parent.parent
STOCK = ROOT / "linux-port/artifacts/stock-cph2493-August-eu-ota/vendor-ramdisk-unpacked/lib/modules/mediatek-drm.ko"
STOCK_SHA = "2096fbf733dd314d584e1a93e8ccef42888cb99fc149a58c05b12c709dc3926c"
SOURCE = ROOT / "linux-port/sources/oneplus-mt6983-kernel-13.1"
SOURCE_COMMIT = "81ec42ad5e803be0cba619f9f7bb298db7d33d7b"
SOURCE_PATH = "drivers/gpu/drm/mediatek/mediatek_v2/mtk_dsi.c"
OUT = ROOT / "linux-port/artifacts/dsi-no-lk-v51-offline"
MODULE = OUT / "mediatek-drm-no-lk.ko"
TEXT_FILE_OFFSET = 0x1000
PATCHES = {
    # Skip the extra runtime-PM reference assumed to exist from Little Kernel.
    0xBAE94: (bytes.fromhex("88000035"), bytes.fromhex("04000014")),
    # Skip early PHY/clock enables; first real modeset must bring them up.
    0xBAEB8: (bytes.fromhex("a8060035"), bytes.fromhex("35000014")),
    # Leave output_en and clk_refcnt at zero instead of presuming active LK DSI.
    0xBAF90: (bytes.fromhex("29008052"), bytes.fromhex("09008052")),
}
KERNEL = "5.10.149-android12-9-o-g311738fbb5a8"


def run(*argv, cwd=None):
    return subprocess.run(argv, cwd=cwd, check=True, capture_output=True,
                          text=True).stdout


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    stock = STOCK.read_bytes()
    if sha(stock) != STOCK_SHA:
        raise RuntimeError("stock DRM module hash changed")
    if run("git", "rev-parse", "HEAD", cwd=SOURCE).strip() != SOURCE_COMMIT:
        raise RuntimeError("matching kernel source checkout changed")
    source = run("git", "show", "HEAD:" + SOURCE_PATH, cwd=SOURCE)
    probe = source.split("static int mtk_dsi_probe(", 1)[1].split("static int mtk_dsi_remove(", 1)[0]
    required = ("/* Assume DSI0 enable already in LK */", "pm_runtime_get_sync(dev);",
                "phy_power_on(dsi->phy);", "dsi->output_en = true;",
                "dsi->clk_refcnt = 1;")
    if not all(item in probe for item in required):
        raise RuntimeError("source no longer contains expected LK handoff")
    sections = run("readelf", "-W", "-S", str(STOCK))
    if not any(".text" in line and "001000 161b00" in line for line in sections.splitlines()):
        raise RuntimeError("stock ELF text layout changed")
    symbols = run("readelf", "-W", "-s", str(STOCK))
    if "00000000000ba938  2456 FUNC" not in symbols or " mtk_dsi_probe" not in symbols:
        raise RuntimeError("mtk_dsi_probe symbol layout changed")
    relocations = run("readelf", "-W", "-r", str(STOCK))
    for offset in PATCHES:
        if any(line.startswith(f"{offset:016x} ") for line in relocations.splitlines()):
            raise RuntimeError(f"patch site {offset:#x} has relocation")
    if not run("modinfo", "-F", "vermagic", str(STOCK)).startswith(KERNEL + " "):
        raise RuntimeError("kernel ABI changed")
    candidate = bytearray(stock)
    for offset, (before, after) in PATCHES.items():
        start = TEXT_FILE_OFFSET + offset
        if candidate[start:start + 4] != before:
            raise RuntimeError(f"stock instruction changed at {offset:#x}")
        candidate[start:start + 4] = after
    MODULE.write_bytes(candidate)
    changed = [i for i, (old, new) in enumerate(zip(stock, candidate)) if old != new]
    allowed = {TEXT_FILE_OFFSET + address + index
               for address in PATCHES for index in range(4)}
    if not changed or any(index not in allowed for index in changed):
        raise RuntimeError("unexpected changed bytes")
    if run("readelf", "-W", "-s", str(MODULE)) != symbols or \
       run("readelf", "-W", "-r", str(MODULE)) != relocations:
        raise RuntimeError("ELF symbols or relocations changed")
    if run("modinfo", "-F", "vermagic", str(MODULE)) != run("modinfo", "-F", "vermagic", str(STOCK)) or \
       run("modinfo", "-F", "depends", str(MODULE)) != run("modinfo", "-F", "depends", str(STOCK)):
        raise RuntimeError("module ABI metadata changed")
    report = {
        "state": "offline-module-candidate-built-not-loaded",
        "source_commit": SOURCE_COMMIT,
        "stock_sha256": STOCK_SHA,
        "candidate_sha256": sha(candidate),
        "stock_module": str(STOCK),
        "candidate_module": str(MODULE),
        "patches": [{"text_offset": hex(offset), "file_offset": hex(TEXT_FILE_OFFSET + offset),
                     "stock": before.hex(), "candidate": after.hex()}
                    for offset, (before, after) in PATCHES.items()],
        "changed_byte_offsets": [hex(index) for index in changed],
        "boot_partition_writes": False,
        "phone_contacted": False,
        "caution": "ELF build-id remains stock; candidate must be identified by SHA-256",
    }
    (OUT / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"state": report["state"], "candidate_sha256": report["candidate_sha256"]}))


if __name__ == "__main__":
    main()
