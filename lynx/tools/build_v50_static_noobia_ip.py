#!/usr/bin/env python3
"""Build an offline V50 with Lynx's rescue and Alpine handoff on .107.

Only the V49 supplement's Wi-Fi address setup changes. This never contacts
Lynx or writes a partition.
"""

import difflib
import gzip
import hashlib
import json
import os
from pathlib import Path
import struct
import time

import build_health_stage_candidate as stage


PORT = stage.PORT
BASE = PORT / "artifacts/iommu-before-cmdq-v49-offline/nord3-iommu-before-cmdq-v49-untested.img"
OUT = PORT / "artifacts/static-noobia-ip-v50-offline"
BASE_SHA = "896aa4937b168090cd3c75d41995917dad05aedfbc7bf83790fe31342b061e0f"
INIT_SHA = "b560f233f5ecf838b5e948d0cd3685b676a84f3097adb00d2c8bfa6e5446ab1f"
RUNTIME = "etc/lynx/wifi-runtime.sh"
ADDRESS = "192.168.100.107"
OLD = b"""    lynx_stage DHCP
    dhcp_bound=0
    for dhcp_attempt in 1 2 3; do
        log "V47_DHCP_ATTEMPT attempt=$dhcp_attempt"
        if $BB udhcpc -f -n -q -t 6 -T 4 -i "$wifi_interface" -x hostname:lynx -s /bin/lynx-dhcp; then
            dhcp_bound=1
            break
        fi
        log "V47_DHCP_RETRY_AFTER_FAILURE attempt=$dhcp_attempt"
        [ "$dhcp_attempt" = 3 ] || $BB sleep 3
    done
    [ "$dhcp_bound" = 1 ] || return 144
    address=$($BB cat /run/lynx/address) || return 145
"""
NEW = b"""    lynx_stage STATIC_NOOBIA_IPV4
    # .107 follows the recorded static .105 Argus and .106 Nexus addresses.
    # Set the rescue address before Dropbear and retain it through Alpine.
    $BB ifconfig "$wifi_interface" 192.168.100.107 netmask 255.255.255.0 up || return 144
    $BB ip route replace default via 192.168.100.1 dev "$wifi_interface" || return 144
    printf 'nameserver 185.82.217.89\\nnameserver 8.8.8.8\\n' > /etc/resolv.conf || return 144
    address=192.168.100.107
    printf '%s\\n' "$address" > /run/lynx/address || return 145
    log "LYNX_STATIC_NOOBIA_IP interface=$wifi_interface address=$address"
"""


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    from image_formats import read_boot_v4, read_newc, require
    from ramdisk_codec import decompress

    os.umask(0o077)
    require(not OUT.exists(), "refuse to overwrite V50 artifact")
    base = BASE.read_bytes()
    require(len(base) == 67_108_864 and sha(base) == BASE_SHA,
            "exact working V49 base absent")
    recipe = json.loads((PORT / "known-good-v19/recipe.json").read_text())
    offset, coverage = recipe["payload_offset"], recipe["coverage_bytes"]
    boot = read_boot_v4(base)
    primary = read_newc(decompress(boot["ramdisk"]))
    require(sha(primary["init"]["data"]) == INIT_SHA,
            "V49 init mismatch")
    old_size = int(primary["etc/lynx/payload-bytes"]["data"].strip())
    old_payload = base[offset:offset + old_size]
    require(sha(old_payload) == primary["etc/lynx/payload-sha256"]["data"].strip().decode(),
            "V49 supplement checksum mismatch")
    members = read_newc(gzip.decompress(old_payload))
    old_runtime = members[RUNTIME]["data"]
    require(old_runtime.count(OLD) == 1 and ADDRESS.encode() not in old_runtime,
            "V49 DHCP block is not the expected one")
    members[RUNTIME] = {**members[RUNTIME], "data": old_runtime.replace(OLD, NEW)}
    payload = gzip.compress(decompress(stage.packed(members)), compresslevel=9, mtime=0)
    require(offset + max(old_size, len(payload)) < len(base) - 4096,
            "V50 supplement exceeds reserved space")
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
    require(len(loaded) <= coverage, "V50 primary overlaps preserved tail")
    image = bytearray(loaded.ljust(coverage, b"\0") + base[coverage:])
    image[offset:offset + max(old_size, len(payload))] = payload.ljust(
        max(old_size, len(payload)), b"\0")
    image = bytes(image)
    require(len(image) == len(base) and
            image[offset + max(old_size, len(payload)):] ==
            base[offset + max(old_size, len(payload)):],
            "V50 tail changed")
    reread = read_boot_v4(image)
    reread_primary = read_newc(decompress(reread["ramdisk"]))
    reread_size = int(reread_primary["etc/lynx/payload-bytes"]["data"].strip())
    reread_members = read_newc(gzip.decompress(image[offset:offset + reread_size]))
    require(reread["kernel"] == boot["kernel"] and
            reread["cmdline"] == boot["cmdline"] and
            reread_primary == primary and reread_members == members,
            "V50 roundtrip failed")
    OUT.mkdir(mode=0o700)
    target = OUT / "nord3-static-noobia-ip-v50-untested.img"
    target.write_bytes(image)
    target.chmod(0o600)
    (OUT / "wifi-runtime.patch").write_text("".join(difflib.unified_diff(
        old_runtime.decode().splitlines(True), members[RUNTIME]["data"].decode().splitlines(True),
        fromfile="V49/wifi-runtime.sh", tofile="V50/wifi-runtime.sh")))
    result = {"state": "offline-v50-candidate-built", "created_ns": time.time_ns(),
              "parent_v49_sha256": BASE_SHA, "image_sha256": sha(image),
              "init_sha256": INIT_SHA, "kernel_sha256": sha(boot["kernel"]),
              "old_payload_bytes": old_size, "new_payload_bytes": len(payload),
              "static_ip": ADDRESS,
              "changed_primary_members": ["etc/lynx/payload-bytes", "etc/lynx/payload-sha256"],
              "changed_supplement_members": [RUNTIME],
              "boot_partition_writes": False, "phone_contacted": False}
    (OUT / "build-result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"image": str(target), "sha256": result["image_sha256"]}))


if __name__ == "__main__":
    main()
