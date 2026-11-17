#!/usr/bin/env python3
"""Build an offline boot_a-only V51 with the DSI no-LK module candidate."""

import gzip
import hashlib
import json
import os
from pathlib import Path
import struct
import time

import build_health_stage_candidate as stage
from build_v51_dsi_cold_init_module import MODULE, STOCK_SHA
from image_formats import read_boot_v4, read_newc, require
from ramdisk_codec import decompress


ROOT = Path(__file__).resolve().parent.parent
PORT = ROOT / "linux-port"
BASE = PORT / "artifacts/static-noobia-ip-v50-offline/nord3-static-noobia-ip-v50-untested.img"
BASE_SHA = "6168cd6288679a321a4d8bc41c7d3dde64a49d3cfe855b8e44542f3307fd5a59"
MODULE_SHA = "d7d522ee81fcc41fe4e4f86f34857475ec3d3ae170b37184ff6420420f822dd8"
TARGET_MEMBER = "lib/modules/mediatek-drm.ko"
OUT = PORT / "artifacts/dsi-no-lk-v51-image-offline"
IMAGE = OUT / "nord3-dsi-no-lk-v51-untested.img"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    os.umask(0o077)
    require(not OUT.exists(), "refuse to overwrite V51 candidate")
    base = BASE.read_bytes()
    require(len(base) == 67_108_864 and sha(base) == BASE_SHA,
            "exact working V50 rollback image absent")
    candidate = MODULE.read_bytes()
    require(sha(candidate) == MODULE_SHA, "validated DSI module candidate changed")
    module_manifest = json.loads((MODULE.parent / "manifest.json").read_text())
    require(module_manifest["stock_sha256"] == STOCK_SHA and
            module_manifest["candidate_sha256"] == MODULE_SHA,
            "DSI module manifest mismatch")
    recipe = json.loads((PORT / "known-good-v19/recipe.json").read_text())
    offset, coverage = recipe["payload_offset"], recipe["coverage_bytes"]
    boot = read_boot_v4(base)
    primary = read_newc(decompress(boot["ramdisk"]))
    old_size = int(primary["etc/lynx/payload-bytes"]["data"].strip())
    old_payload = base[offset:offset + old_size]
    require(sha(old_payload) == primary["etc/lynx/payload-sha256"]["data"].strip().decode(),
            "V50 supplement checksum mismatch")
    members = read_newc(gzip.decompress(old_payload))
    require(TARGET_MEMBER not in members and
            b"mediatek-drm.ko\n" in members["etc/lynx/wifi-radio-modules.load"]["data"],
            "module overlay or load order unexpected")
    stage.put(members, TARGET_MEMBER, candidate, 0o644)
    payload = gzip.compress(decompress(stage.packed(members)), compresslevel=9, mtime=0)
    require(offset + max(old_size, len(payload)) < len(base) - 4096,
            "V51 payload exceeds boot_a image tail")
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
    require(len(loaded) <= coverage, "V51 primary overlaps preserved tail")
    image = bytearray(loaded.ljust(coverage, b"\0") + base[coverage:])
    image[offset:offset + max(old_size, len(payload))] = payload.ljust(
        max(old_size, len(payload)), b"\0")
    image = bytes(image)
    require(len(image) == len(base) and
            image[offset + max(old_size, len(payload)):] ==
            base[offset + max(old_size, len(payload)):],
            "V51 changed bytes beyond supplement")
    reread = read_boot_v4(image)
    reread_primary = read_newc(decompress(reread["ramdisk"]))
    reread_size = int(reread_primary["etc/lynx/payload-bytes"]["data"].strip())
    reread_members = read_newc(gzip.decompress(image[offset:offset + reread_size]))
    require(reread["kernel"] == boot["kernel"] and
            reread["cmdline"] == boot["cmdline"] and
            reread_primary == primary and reread_members == members,
            "V51 archive roundtrip failed")
    original_members = read_newc(gzip.decompress(old_payload))
    added = set(reread_members) - set(original_members)
    require(added == {"lib", "lib/modules", TARGET_MEMBER} and
            all(reread_members[name] == value for name, value in original_members.items()),
            "V51 changed an existing supplement member")
    OUT.mkdir(mode=0o700)
    IMAGE.write_bytes(image)
    IMAGE.chmod(0o600)
    report = {
        "state": "offline-v51-candidate-built-not-flashed",
        "created_ns": time.time_ns(),
        "parent_v50_sha256": BASE_SHA,
        "image_sha256": sha(image),
        "kernel_sha256": sha(boot["kernel"]),
        "module_member": TARGET_MEMBER,
        "module_sha256": MODULE_SHA,
        "old_payload_bytes": old_size,
        "new_payload_bytes": len(payload),
        "changed_primary_members": ["etc/lynx/payload-bytes", "etc/lynx/payload-sha256"],
        "added_supplement_members": ["lib", "lib/modules", TARGET_MEMBER],
        "boot_partition_writes": False,
        "phone_contacted": False,
        "rollback_image": str(BASE),
    }
    (OUT / "build-result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"image": str(IMAGE), "sha256": report["image_sha256"]}))


if __name__ == "__main__":
    main()
