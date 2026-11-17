#!/usr/bin/env python3
"""Independently validate V49's two archive changes against pinned V48."""

import gzip
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "linux-port"))
from image_formats import read_boot_v4, read_newc
from ramdisk_codec import decompress

ROOT = Path(__file__).resolve().parent.parent
PORT = ROOT / "linux-port"
V48 = PORT / "artifacts/no-charger-shutdown-v48-offline/nord3-no-charger-shutdown-v48-untested.img"
OUT = PORT / "artifacts/iommu-before-cmdq-v49-offline"
V49 = OUT / "nord3-iommu-before-cmdq-v49-untested.img"
V48_SHA = "ff1244698cf791546b7c03c2f510882048c91a88f9344e80d583fda388f2340d"
V49_SHA = "896aa4937b168090cd3c75d41995917dad05aedfbc7bf83790fe31342b061e0f"
MODULE_SHA = "f2f2d31ec2dcb769311dfab3621622a7deff7ba83d14c2f5137d94f38c44b332"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def unpack(image, offset):
    boot = read_boot_v4(image)
    primary = read_newc(decompress(boot["ramdisk"]))
    size = int(primary["etc/lynx/payload-bytes"]["data"])
    payload = image[offset:offset + size]
    assert sha(payload) == primary["etc/lynx/payload-sha256"]["data"].strip().decode()
    return boot, primary, read_newc(gzip.decompress(payload)), size


def main():
    old, new = V48.read_bytes(), V49.read_bytes()
    assert len(old) == len(new) == 67_108_864
    assert sha(old) == V48_SHA and sha(new) == V49_SHA
    recipe = json.loads((PORT / "known-good-v19/recipe.json").read_text())
    offset, coverage = recipe["payload_offset"], recipe["coverage_bytes"]
    old_boot, old_primary, old_members, old_size = unpack(old, offset)
    new_boot, new_primary, new_members, new_size = unpack(new, offset)
    assert old_boot["kernel"] == new_boot["kernel"]
    assert old_boot["cmdline"] == new_boot["cmdline"]
    assert old_primary["init"] == new_primary["init"]
    primary_delta = {n for n in old_primary.keys() | new_primary.keys()
                     if old_primary.get(n) != new_primary.get(n)}
    assert primary_delta == {"etc/lynx/payload-bytes", "etc/lynx/payload-sha256"}
    member_delta = {n for n in old_members.keys() | new_members.keys()
                    if old_members.get(n) != new_members.get(n)}
    assert member_delta == {"etc/lynx/wifi-radio-modules.load", "lib/modules/mtk_iommu.ko"}
    assert sha(new_members["lib/modules/mtk_iommu.ko"]["data"]) == MODULE_SHA
    old_list = old_members["etc/lynx/wifi-radio-modules.load"]["data"].splitlines()
    new_list = new_members["etc/lynx/wifi-radio-modules.load"]["data"].splitlines()
    assert new_list == old_list[:old_list.index(b"mtk-cmdq-drv-ext.ko")] + [
        b"mtk_iommu.ko"] + old_list[old_list.index(b"mtk-cmdq-drv-ext.ko"):]
    assert all(new_list.index(x) < new_list.index(b"mtk_iommu.ko") for x in (
        b"emi-mpu.ko", b"emi.ko", b"mtk-smi.ko", b"mtk-smi-dbg.ko",
        b"iommu_secure.ko", b"iommu_debug.ko"))
    assert new_list.index(b"mtk_iommu.ko") < new_list.index(b"mtk-cmdq-drv-ext.ko")
    assert old[offset + max(old_size, new_size):] == new[offset + max(old_size, new_size):]
    assert len(new_boot["ramdisk"]) <= coverage
    build = json.loads((OUT / "build-result.json").read_text())
    assert build["state"] == "offline-v49-candidate-built" and build["image_sha256"] == V49_SHA
    report = {"state": "offline-v49-validation-passed", "image_sha256": V49_SHA,
              "rollback_v48_sha256": V48_SHA, "stock_iommu_sha256": MODULE_SHA,
              "kernel_and_init_unchanged": True,
              "primary_delta": sorted(primary_delta), "supplement_delta": sorted(member_delta),
              "stock_dependencies_before_iommu": True, "iommu_before_cmdq": True,
              "boot_partition_writes": False, "phone_contacted": False}
    (OUT / "validation.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
