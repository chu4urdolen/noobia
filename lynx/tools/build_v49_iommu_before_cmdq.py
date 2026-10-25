#!/usr/bin/env python3
"""Build an offline V49 from pinned V48 with stock IOMMU loaded before CMDQ."""

import difflib
import gzip
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import time

import build_health_stage_candidate as stage


ROOT, PORT = stage.ROOT, stage.PORT
BASE = PORT / "artifacts/no-charger-shutdown-v48-offline/nord3-no-charger-shutdown-v48-untested.img"
OUT = PORT / "artifacts/iommu-before-cmdq-v49-offline"
BASE_SHA = "ff1244698cf791546b7c03c2f510882048c91a88f9344e80d583fda388f2340d"
INIT_SHA = "b560f233f5ecf838b5e948d0cd3685b676a84f3097adb00d2c8bfa6e5446ab1f"
MODULE = PORT / "artifacts/stock-cph2493-August-eu-ota/vendor-ramdisk-unpacked/lib/modules/mtk_iommu.ko"
MODULE_SHA = "f2f2d31ec2dcb769311dfab3621622a7deff7ba83d14c2f5137d94f38c44b332"
MANIFEST = "etc/lynx/wifi-radio-modules.load"
MODPATH = "lib/modules/mtk_iommu.ko"
ANCHOR = b"irq-dbg.ko\nmtk-cmdq-drv-ext.ko\n"
REPLACEMENT = b"irq-dbg.ko\nmtk_iommu.ko\nmtk-cmdq-drv-ext.ko\n"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    from image_formats import read_boot_v4, read_newc, require
    from ramdisk_codec import decompress

    os.umask(0o077)
    require(not OUT.exists(), "refuse to overwrite V49 artifact")
    base = BASE.read_bytes()
    require(len(base) == 67_108_864 and sha(base) == BASE_SHA,
            "exact V48 base absent")
    module = MODULE.read_bytes()
    require(sha(module) == MODULE_SHA, "stock IOMMU module hash mismatch")
    vermagic = subprocess.run(["modinfo", "-F", "vermagic", str(MODULE)],
                             capture_output=True, text=True, check=True).stdout
    require(vermagic.startswith("5.10.149-android12-9-o-g311738fbb5a8 "),
            "stock IOMMU ABI mismatch")

    recipe = json.loads((PORT / "known-good-v19/recipe.json").read_text())
    offset, coverage = recipe["payload_offset"], recipe["coverage_bytes"]
    boot = read_boot_v4(base)
    primary = read_newc(decompress(boot["ramdisk"]))
    require(sha(primary["init"]["data"]) == INIT_SHA, "V48 init mismatch")
    old_size = int(primary["etc/lynx/payload-bytes"]["data"].strip())
    old_payload = base[offset:offset + old_size]
    require(sha(old_payload) == primary["etc/lynx/payload-sha256"]["data"].strip().decode(),
            "V48 supplement checksum mismatch")
    members = read_newc(gzip.decompress(old_payload))
    old_manifest = members[MANIFEST]["data"]
    require(old_manifest.count(ANCHOR) == 1 and MODPATH not in members,
            "unexpected V48 module order or IOMMU already present")
    prior = old_manifest.splitlines()
    require(all(x in prior and prior.index(x) < prior.index(b"mtk-cmdq-drv-ext.ko")
                for x in (b"emi-mpu.ko", b"emi.ko", b"mtk-smi.ko", b"mtk-smi-dbg.ko",
                          b"iommu_secure.ko", b"iommu_debug.ko", b"irq-dbg.ko")),
            "IOMMU dependencies do not precede CMDQ")
    members[MANIFEST] = {**members[MANIFEST],
                         "data": old_manifest.replace(ANCHOR, REPLACEMENT)}
    # Reuse a module file's archive metadata; only the stock bytes are new.
    members[MODPATH] = {**members["lib/modules/ccci_auxadc.ko"], "data": module}
    payload = gzip.compress(decompress(stage.packed(members)), compresslevel=9, mtime=0)
    require(offset + max(old_size, len(payload)) < len(base) - 4096,
            "V49 supplement exceeds reserved space")
    primary["etc/lynx/payload-bytes"] = {
        **primary["etc/lynx/payload-bytes"], "data": (str(len(payload)) + "\n").encode()}
    primary["etc/lynx/payload-sha256"] = {
        **primary["etc/lynx/payload-sha256"], "data": (sha(payload) + "\n").encode()}
    ramdisk = stage.packed(primary)
    header = bytearray(base[:1584])
    struct.pack_into("<I", header, 12, len(ramdisk))
    align = lambda value: (value + 4095) // 4096 * 4096
    loaded = (bytes(header).ljust(4096, b"\0") +
              boot["kernel"].ljust(align(len(boot["kernel"])), b"\0") +
              ramdisk.ljust(align(len(ramdisk)), b"\0"))
    require(len(loaded) <= coverage, "V49 primary overlaps preserved tail")
    image = bytearray(loaded.ljust(coverage, b"\0") + base[coverage:])
    image[offset:offset + max(old_size, len(payload))] = payload.ljust(
        max(old_size, len(payload)), b"\0")
    image = bytes(image)
    require(len(image) == len(base) and
            image[offset + max(old_size, len(payload)):] ==
            base[offset + max(old_size, len(payload)):], "V49 tail changed")
    reread = read_boot_v4(image)
    reread_primary = read_newc(decompress(reread["ramdisk"]))
    reread_size = int(reread_primary["etc/lynx/payload-bytes"]["data"].strip())
    reread_members = read_newc(gzip.decompress(image[offset:offset + reread_size]))
    require(reread["kernel"] == boot["kernel"] and
            reread["cmdline"] == boot["cmdline"] and
            reread_primary == primary and reread_members == members and
            reread_primary["init"]["data"] == read_newc(decompress(boot["ramdisk"]))["init"]["data"],
            "V49 roundtrip or scope check failed")

    OUT.mkdir(mode=0o700)
    target = OUT / "nord3-iommu-before-cmdq-v49-untested.img"
    target.write_bytes(image)
    target.chmod(0o600)
    (OUT / "wifi-radio-modules.patch").write_text("".join(difflib.unified_diff(
        old_manifest.decode().splitlines(True), members[MANIFEST]["data"].decode().splitlines(True),
        fromfile="V48/wifi-radio-modules.load", tofile="V49/wifi-radio-modules.load")))
    result = {"state": "offline-v49-candidate-built", "created_ns": time.time_ns(),
              "parent_v48_sha256": BASE_SHA, "image_sha256": sha(image),
              "init_sha256": INIT_SHA, "kernel_sha256": sha(boot["kernel"]),
              "stock_iommu_module_sha256": MODULE_SHA, "old_payload_bytes": old_size,
              "new_payload_bytes": len(payload),
              "changed_primary_members": ["etc/lynx/payload-bytes", "etc/lynx/payload-sha256"],
              "changed_supplement_members": [MANIFEST, MODPATH],
              "boot_partition_writes": False, "phone_contacted": False,
              "limit": "Offline candidate only; load order and display behavior require a controlled boot trial."}
    (OUT / "build-result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"image": str(target), "sha256": result["image_sha256"]}))


if __name__ == "__main__":
    main()
