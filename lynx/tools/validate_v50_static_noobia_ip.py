#!/usr/bin/env python3
"""Independent image-scope checks for Lynx V50 static IPv4 candidate."""

import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "linux-port"))
from image_formats import read_boot_v4, read_newc, require
from ramdisk_codec import decompress


PORT = Path(__file__).resolve().parent.parent / "linux-port"
BASE = PORT / "artifacts/iommu-before-cmdq-v49-offline/nord3-iommu-before-cmdq-v49-untested.img"
OUT = PORT / "artifacts/static-noobia-ip-v50-offline"
IMAGE = OUT / "nord3-static-noobia-ip-v50-untested.img"
RUNTIME = "etc/lynx/wifi-runtime.sh"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def unpack(image, offset):
    boot = read_boot_v4(image)
    primary = read_newc(decompress(boot["ramdisk"]))
    size = int(primary["etc/lynx/payload-bytes"]["data"].strip())
    payload = image[offset:offset + size]
    require(sha(payload) == primary["etc/lynx/payload-sha256"]["data"].strip().decode(),
            "supplement hash mismatch")
    return boot, primary, read_newc(gzip.decompress(payload)), size


def main():
    recipe = json.loads((PORT / "known-good-v19/recipe.json").read_text())
    build = json.loads((OUT / "build-result.json").read_text())
    old, new = BASE.read_bytes(), IMAGE.read_bytes()
    require(len(old) == len(new) == 67_108_864, "partition-size drift")
    require(sha(old) == "896aa4937b168090cd3c75d41995917dad05aedfbc7bf83790fe31342b061e0f",
            "V49 parent drift")
    require(sha(new) == build["image_sha256"], "V50 output hash mismatch")
    offset, coverage = recipe["payload_offset"], recipe["coverage_bytes"]
    old_boot, old_primary, old_members, old_size = unpack(old, offset)
    new_boot, new_primary, new_members, new_size = unpack(new, offset)
    require(old_boot["kernel"] == new_boot["kernel"] and
            old_boot["cmdline"] == new_boot["cmdline"],
            "kernel or command line changed")
    require(sha(old_primary["init"]["data"]) ==
            sha(new_primary["init"]["data"]) ==
            "b560f233f5ecf838b5e948d0cd3685b676a84f3097adb00d2c8bfa6e5446ab1f",
            "rescue init changed")
    primary_changes = {key for key in old_primary.keys() | new_primary.keys()
                       if old_primary.get(key) != new_primary.get(key)}
    member_changes = {key for key in old_members.keys() | new_members.keys()
                      if old_members.get(key) != new_members.get(key)}
    require(primary_changes == {"etc/lynx/payload-bytes", "etc/lynx/payload-sha256"},
            "unexpected primary ramdisk change")
    require(member_changes == {RUNTIME}, "unexpected supplement change")
    require(old_members[RUNTIME]["mode"] == new_members[RUNTIME]["mode"],
            "runtime permissions changed")
    runtime = new_members[RUNTIME]["data"]
    require(runtime.count(b"192.168.100.107") == 2 and
            b"udhcpc -f" not in runtime and
            b"lynx_stage STATIC_NOOBIA_IPV4" in runtime and
            b"ip route replace default via 192.168.100.1" in runtime,
            "static address path malformed")
    syntax = subprocess.run(["sh", "-n"], input=runtime, capture_output=True)
    require(syntax.returncode == 0, "V50 Wi-Fi shell syntax error")
    end = offset + max(old_size, new_size)
    require(new[coverage:offset] == old[coverage:offset] and
            new[end:] == old[end:], "reserved tail or other partitions changed")
    result = {"state": "offline-v50-validation-passed",
              "v49_sha256": sha(old), "v50_sha256": sha(new),
              "kernel_sha256": sha(new_boot["kernel"]),
              "changed_primary_members": sorted(primary_changes),
              "changed_supplement_members": sorted(member_changes),
              "static_ip": "192.168.100.107", "phone_contacted": False,
              "boot_partition_writes": False}
    (OUT / "validation.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
