#!/usr/bin/env python3
"""Build an offline V52 derivative that waits before Wi-Fi power-on.

This isolates a possible asynchronous shared-radio pre-calibration race. It
does not establish that the race caused any earlier Fastboot return.
"""

import gzip
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
PORT = ROOT / "linux-port"
sys.path.insert(0, str(PORT))
import build_health_stage_candidate as stage
from image_formats import read_boot_v4, read_newc, require
from ramdisk_codec import decompress

V52 = PORT / "artifacts/bt-before-wifi-v52-offline/nord3-bt-before-wifi-v52-untested.img"
OUT = PORT / "artifacts/bt-precal-settle-v53-offline"
V52_SHA = "9206aafb339ad66b2d942ea5795b8f476a5eaf3a148f9cdfc76be22cb83e30bf"
V50_SHA = "6168cd6288679a321a4d8bc41c7d3dde64a49d3cfe855b8e44542f3307fd5a59"
INIT_SHA = "b560f233f5ecf838b5e948d0cd3685b676a84f3097adb00d2c8bfa6e5446ab1f"
SCRIPT = "etc/lynx/wifi-runtime.sh"
OLD = b"    lynx_stage WIFI_STATION_POWER_ON\n"
NEW = (b"    lynx_stage BT_PRECAL_SETTLE_WAIT\n"
       b"    $BB sleep 30\n"
       b"    lynx_stage WIFI_STATION_POWER_ON\n")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    os.umask(0o077)
    require(not OUT.exists(), "refuse to overwrite existing V53 artifact")
    parent = V52.read_bytes()
    require(len(parent) == 67_108_864 and sha(parent) == V52_SHA,
            "exact V52 parent absent")
    rollback = PORT / "artifacts/static-noobia-ip-v50-offline/nord3-static-noobia-ip-v50-untested.img"
    require(rollback.is_file() and sha(rollback.read_bytes()) == V50_SHA,
            "exact V50 rollback absent")
    recipe = json.loads((PORT / "known-good-v19/recipe.json").read_text())
    offset, coverage = recipe["payload_offset"], recipe["coverage_bytes"]
    boot = read_boot_v4(parent)
    primary = read_newc(decompress(boot["ramdisk"]))
    require(sha(primary["init"]["data"]) == INIT_SHA, "rescue init changed")
    old_size = int(primary["etc/lynx/payload-bytes"]["data"].strip())
    old_payload = parent[offset:offset + old_size]
    require(sha(old_payload) == primary["etc/lynx/payload-sha256"]["data"].strip().decode(),
            "parent supplement checksum mismatch")
    old_members = read_newc(gzip.decompress(old_payload))
    members = {name: dict(entry) for name, entry in old_members.items()}
    script = members[SCRIPT]["data"]
    require(script.count(OLD) == 1 and b"BT_PRECAL_SETTLE_WAIT" not in script,
            "unexpected parent Wi-Fi runtime")
    require(members["etc/lynx/wifi-radio-modules.load"]["data"].endswith(
        b"wlan_drv_gen4m_6983.ko\nbtif_drv.ko\nbt_drv_6983.ko\n"),
        "Bluetooth registration order changed")
    members[SCRIPT]["data"] = script.replace(OLD, NEW)
    payload = gzip.compress(decompress(stage.packed(members)), compresslevel=9, mtime=0)
    require(offset + max(old_size, len(payload)) < len(parent) - 4096,
            "new supplement exceeds reserved space")
    primary["etc/lynx/payload-bytes"]["data"] = (str(len(payload)) + "\n").encode()
    primary["etc/lynx/payload-sha256"]["data"] = (sha(payload) + "\n").encode()
    ramdisk = stage.packed(primary)
    header = bytearray(parent[:1584])
    struct.pack_into("<I", header, 12, len(ramdisk))
    align = lambda n: (n + 4095) // 4096 * 4096
    loaded = (bytes(header).ljust(4096, b"\0") +
              boot["kernel"].ljust(align(len(boot["kernel"])), b"\0") +
              ramdisk.ljust(align(len(ramdisk)), b"\0"))
    require(len(loaded) <= coverage, "primary overlaps preserved tail")
    image = bytearray(loaded.ljust(coverage, b"\0") + parent[coverage:])
    image[offset:offset + max(old_size, len(payload))] = payload.ljust(
        max(old_size, len(payload)), b"\0")
    image = bytes(image)
    reread = read_boot_v4(image)
    reread_primary = read_newc(decompress(reread["ramdisk"]))
    reread_size = int(reread_primary["etc/lynx/payload-bytes"]["data"].strip())
    reread_members = read_newc(gzip.decompress(image[offset:offset + reread_size]))
    require(len(image) == len(parent) and reread["kernel"] == boot["kernel"] and
            reread["cmdline"] == boot["cmdline"] and reread_primary == primary and
            reread_members == members and set(reread_members) == set(old_members) and
            {name for name in members if members[name] != old_members[name]} == {SCRIPT} and
            image[offset + max(old_size, len(payload)):] ==
            parent[offset + max(old_size, len(payload)):],
            "V53 roundtrip or change-scope check failed")
    OUT.mkdir(mode=0o700)
    target = OUT / "nord3-bt-precal-settle-v53-untested.img"
    target.write_bytes(image)
    target.chmod(0o600)
    report = {
        "state": "offline-v53-candidate-built", "created_ns": time.time_ns(),
        "parent_v52_sha256": V52_SHA, "rollback_v50_sha256": V50_SHA,
        "image_sha256": sha(image), "kernel_sha256": sha(boot["kernel"]),
        "init_sha256": INIT_SHA, "settle_wait_seconds": 30,
        "changed_supplement_members": [SCRIPT], "added_supplement_members": [],
        "boot_partition_writes": False, "phone_contacted": False,
        "hypothesis": "asynchronous calibration may race Wi-Fi station power-on",
    }
    (OUT / "build-result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"image": str(target), "sha256": report["image_sha256"]}))


if __name__ == "__main__":
    main()
