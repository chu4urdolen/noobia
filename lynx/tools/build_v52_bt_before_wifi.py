#!/usr/bin/env python3
"""Build an offline V52 trial that registers Bluetooth before Wi-Fi power-on."""

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

BASE = PORT / "artifacts/static-noobia-ip-v50-offline/nord3-static-noobia-ip-v50-untested.img"
OUT = PORT / "artifacts/bt-before-wifi-v52-offline"
BASE_SHA = "6168cd6288679a321a4d8bc41c7d3dde64a49d3cfe855b8e44542f3307fd5a59"
INIT_SHA = "b560f233f5ecf838b5e948d0cd3685b676a84f3097adb00d2c8bfa6e5446ab1f"
STOCK = PORT / "artifacts/stock-cph2493-August-eu-ota/wifi-reference/vendor-dlkm-unpacked/lib/modules"
FIRMWARE = PORT / "artifacts/stock-cph2493-August-eu-ota/wifi-reference/vendor-unpacked/firmware"
EXPECTED_MODULES = {
    "btif_drv.ko": "f81ec909db5e986b2a8e23fa1c34f3f3a027a07e2da5335fc3917b8bf9615d51",
    "bt_drv_6983.ko": "f6c99218edc8e903b2ccbaac7f9e7176cd11b6129350ff738fb64d1b9ade5296",
}
RADIO_LIST = "etc/lynx/wifi-radio-modules.load"
BT_CONFIG = "lib/firmware/BT_FW.cfg"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    os.umask(0o077)
    require(not OUT.exists(), "refuse to overwrite V52 artifact")
    base = BASE.read_bytes()
    require(len(base) == 67_108_864 and sha(base) == BASE_SHA,
            "exact working V50 image absent")
    recipe = json.loads((PORT / "known-good-v19/recipe.json").read_text())
    offset, coverage = recipe["payload_offset"], recipe["coverage_bytes"]
    boot = read_boot_v4(base)
    primary = read_newc(decompress(boot["ramdisk"]))
    require(sha(primary["init"]["data"]) == INIT_SHA,
            "V50 rescue init mismatch")
    old_size = int(primary["etc/lynx/payload-bytes"]["data"].strip())
    old_payload = base[offset:offset + old_size]
    require(sha(old_payload) == primary["etc/lynx/payload-sha256"]["data"].strip().decode(),
            "V50 supplement checksum mismatch")
    members = read_newc(gzip.decompress(old_payload))
    old_members = {name: dict(entry) for name, entry in members.items()}
    old_keys = set(members)
    old_radio = members[RADIO_LIST]["data"]
    require(old_radio.endswith(b"wlan_drv_gen4m_6983.ko\n") and
            b"bt_drv_6983.ko" not in old_radio and b"btif_drv.ko" not in old_radio,
            "unexpected V50 radio load order")
    require(members["lib/firmware/conninfra.cfg"]["data"].strip().endswith(b"pre_cal_mode=3"),
            "stock calibration mode differs")

    for name, digest in EXPECTED_MODULES.items():
        data = (STOCK / name).read_bytes()
        require(sha(data) == digest, "stock Bluetooth module changed: " + name)
        stage.put(members, "lib/modules/" + name, data, 0o644)
    config = (FIRMWARE / "BT_FW.cfg").read_bytes()
    stage.put(members, BT_CONFIG, config, 0o644)
    members[RADIO_LIST] = {
        **members[RADIO_LIST],
        "data": old_radio + b"btif_drv.ko\nbt_drv_6983.ko\n",
    }
    payload = gzip.compress(decompress(stage.packed(members)), compresslevel=9, mtime=0)
    require(offset + max(old_size, len(payload)) < len(base) - 4096,
            "V52 supplement exceeds reserved space")
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
    require(len(loaded) <= coverage, "V52 primary overlaps preserved tail")
    image = bytearray(loaded.ljust(coverage, b"\0") + base[coverage:])
    image[offset:offset + max(old_size, len(payload))] = payload.ljust(
        max(old_size, len(payload)), b"\0")
    image = bytes(image)
    require(len(image) == len(base) and
            image[offset + max(old_size, len(payload)):] ==
            base[offset + max(old_size, len(payload)):],
            "V52 tail changed")
    reread = read_boot_v4(image)
    reread_primary = read_newc(decompress(reread["ramdisk"]))
    reread_size = int(reread_primary["etc/lynx/payload-bytes"]["data"].strip())
    reread_members = read_newc(gzip.decompress(image[offset:offset + reread_size]))
    require(reread["kernel"] == boot["kernel"] and
            reread["cmdline"] == boot["cmdline"] and
            reread_primary == primary and reread_members == members,
            "V52 roundtrip failed")
    changed = {name for name in old_keys if members[name] != old_members[name]}
    require(changed == {RADIO_LIST}, "unintended supplement member changed")
    require(set(members) - old_keys == {
        "lib", "lib/modules", "lib/modules/btif_drv.ko",
        "lib/modules/bt_drv_6983.ko", BT_CONFIG},
        "unintended supplement member added")

    OUT.mkdir(mode=0o700)
    target = OUT / "nord3-bt-before-wifi-v52-untested.img"
    target.write_bytes(image)
    target.chmod(0o600)
    report = {
        "state": "offline-v52-candidate-built", "created_ns": time.time_ns(),
        "parent_v50_sha256": BASE_SHA, "image_sha256": sha(image),
        "kernel_sha256": sha(boot["kernel"]), "init_sha256": INIT_SHA,
        "old_payload_bytes": old_size, "new_payload_bytes": len(payload),
        "new_modules_sha256": EXPECTED_MODULES,
        "stock_bt_config_sha256": sha(config),
        "radio_order_tail": members[RADIO_LIST]["data"].decode().splitlines()[-4:],
        "changed_supplement_members": sorted(changed),
        "added_supplement_members": sorted(set(members) - old_keys),
        "boot_partition_writes": False, "phone_contacted": False,
    }
    (OUT / "build-result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"image": str(target), "sha256": report["image_sha256"]}))


if __name__ == "__main__":
    main()
