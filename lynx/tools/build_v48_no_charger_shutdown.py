#!/usr/bin/env python3
"""Build a V48 boot_a candidate by removing V47's charger boot refusal.

The exact V47 kernel, supplement, bootloader, recovery and slot B are untouched.
This writes only an offline 64 MiB candidate and review receipts.
"""

import difflib
import gzip
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import time

import build_health_stage_candidate as stage


ROOT, PORT = stage.ROOT, stage.PORT
BASE = PORT / "artifacts/wifi-dhcp-retry-v47-offline"
OUT = PORT / "artifacts/no-charger-shutdown-v48-offline"
BASE_SHA = "c969e1938b051ab03b49ad4f2260e900e9e336997d1026ca00c3a493dedde066"
INIT_SHA = "ebc6bb746aaf710d915c47036f92ce0c4ed23a185dfb5349b90e654bab7ba4ae"

FIRST = b'''    v40_supplies=0
    for v40_supply in /sys/class/power_supply/*; do
        [ -r "$v40_supply/online" ] || continue
        IFS= read -r v40_online < "$v40_supply/online" || stop
        [ "$v40_online" = 0 ] || {
            lynx_bootdiag_append CHARGER_ON || true
            log 'V41_CHARGER_ONLINE; POWER_OFF_REQUESTED'
            $BB poweroff -f
            /bin/boot-proof-reboot
            stop
        }
        v40_supplies=$((v40_supplies+1))
    done
    [ "$v40_supplies" -ge 1 ] || stop
    $BB sleep 5
'''
FIRST_NEW = b'''    # V48: permit powered boot; thermal and battery watchers remain active.
    $BB sleep 5
'''
SECOND = b'''(
    while :; do
        v40_guard_count=0
        v40_guard_ok=1
        for v40_guard_supply in /sys/class/power_supply/*; do
            [ -r "$v40_guard_supply/online" ] || continue
            IFS= read -r v40_guard_online < "$v40_guard_supply/online" || {
                v40_guard_ok=0
                break
            }
            [ "$v40_guard_online" = 0 ] || {
                v40_guard_ok=0
                break
            }
            v40_guard_count=$((v40_guard_count+1))
        done
        [ "$v40_guard_count" -ge 1 ] && [ "$v40_guard_ok" = 1 ] || {
            log 'V41_CHARGER_GUARD_POWER_OFF'
            $BB poweroff -f
            /bin/boot-proof-reboot
        }
        $BB sleep 5
    done
) >/run/lynx/v40-charger-guard.log 2>&1 </dev/null &
v40_charger_guard=$!
printf '%s\\n' "$v40_charger_guard" > /run/lynx/v40-charger-guard.pid || stop
'''
SECOND_NEW = b'''log 'V48_CHARGER_SHUTDOWN_REMOVED; HEALTH_WATCHERS_ACTIVE'
'''
HEALTH_MEMBER = "usr/libexec/lynx/autonomous-health-start.sh"
HEALTH_OLD = b'''        offline_supplies=0
        for supply in /sys/class/power_supply/*; do
            [ -r "$supply/online" ] || continue
            online=$(cat "$supply/online") || fail 'charger state unreadable'
            [ "$online" = 0 ] || fail 'USB or charger is online; charging unvalidated'
            offline_supplies=$((offline_supplies+1))
        done
        [ "$offline_supplies" -ge 1 ] || fail 'no charger state available';;
'''
HEALTH_NEW = b'''        say 'V48_CHARGER_BOOT_ALLOWED';;
'''


def main():
    from image_formats import read_boot_v4, read_newc, require
    from ramdisk_codec import decompress

    os.umask(0o077)
    require(not OUT.exists(), "refuse to overwrite V48 artifact")
    base = (BASE / "nord3-wifi-dhcp-retry-v47-untested.img").read_bytes()
    base_result = json.loads((BASE / "build-result.json").read_text())
    base_validation = json.loads((BASE / "validation.json").read_text())
    require(len(base) == 67_108_864 and stage.sha(base) == BASE_SHA ==
            base_result["image_sha256"] == base_validation["image_sha256"] and
            base_validation["state"] == "offline-v47-validation-passed",
            "exact validated V47 base absent")
    recipe = json.loads((PORT / "known-good-v19/recipe.json").read_text())
    offset, coverage = recipe["payload_offset"], recipe["coverage_bytes"]
    require(coverage <= offset < len(base) - 4096, "unexpected supplement boundary")
    boot = read_boot_v4(base)
    primary = read_newc(decompress(boot["ramdisk"]))
    old_size = int(primary["etc/lynx/payload-bytes"]["data"].strip())
    old_payload = base[offset:offset + old_size]
    require(stage.sha(old_payload) ==
            primary["etc/lynx/payload-sha256"]["data"].strip().decode(),
            "V47 supplement checksum mismatch")
    members = read_newc(gzip.decompress(old_payload))
    health_before = members[HEALTH_MEMBER]["data"]
    require(health_before.count(HEALTH_OLD) == 1,
            "health charger refusal block not unique")
    health_after = health_before.replace(HEALTH_OLD, HEALTH_NEW)
    require(subprocess.run(["busybox", "sh", "-n"], input=health_after,
                           capture_output=True, timeout=20).returncode == 0,
            "health startup syntax invalid")
    members[HEALTH_MEMBER] = {**members[HEALTH_MEMBER], "data": health_after}
    payload = gzip.compress(decompress(stage.packed(members)), compresslevel=9, mtime=0)
    require(offset + max(old_size, len(payload)) < len(base) - 4096,
            "V48 supplement exceeds reserved space")
    original = primary["init"]["data"]
    require(stage.sha(original) == INIT_SHA, "V47 init hash mismatch")
    require(original.count(FIRST) == 1 and original.count(SECOND) == 1,
            "charger shutdown blocks did not match exactly")
    changed = original.replace(FIRST, FIRST_NEW).replace(SECOND, SECOND_NEW)
    require(b"V41_CHARGER_GUARD_POWER_OFF" not in changed and
            b"V41_CHARGER_ONLINE; POWER_OFF_REQUESTED" not in changed and
            b"v40_charger_guard" not in changed and
            b"lynx_autonomous_health_local_handoff" in changed and
            b"lynx_persistent_openrc_handoff" in changed,
            "unexpected charger or health content after edit")
    syntax = subprocess.run(["busybox", "sh", "-n"], input=changed,
                            capture_output=True, timeout=20)
    require(syntax.returncode == 0, "V48 init shell syntax failed")
    primary["init"] = {**primary["init"], "data": changed}
    primary["etc/lynx/payload-bytes"] = {
        **primary["etc/lynx/payload-bytes"], "data": (str(len(payload)) + "\n").encode()}
    primary["etc/lynx/payload-sha256"] = {
        **primary["etc/lynx/payload-sha256"], "data": (stage.sha(payload) + "\n").encode()}
    ramdisk = stage.packed(primary)
    header = bytearray(base[:1584])
    struct.pack_into("<I", header, 12, len(ramdisk))
    align = lambda value: (value + 4095) // 4096 * 4096
    loaded = (bytes(header).ljust(4096, b"\0") +
              boot["kernel"].ljust(align(len(boot["kernel"])), b"\0") +
              ramdisk.ljust(align(len(ramdisk)), b"\0"))
    require(len(loaded) <= coverage, "V48 primary overlaps preserved tail")
    image = bytearray(loaded.ljust(coverage, b"\0") + base[coverage:])
    image[offset:offset + max(old_size, len(payload))] = payload.ljust(
        max(old_size, len(payload)), b"\0")
    image = bytes(image)
    require(len(image) == len(base) and
            image[offset + max(old_size, len(payload)):] ==
            base[offset + max(old_size, len(payload)):],
            "V48 tail changed")
    new_boot = read_boot_v4(image)
    new_primary = read_newc(decompress(new_boot["ramdisk"]))
    reread_size = int(new_primary["etc/lynx/payload-bytes"]["data"].strip())
    new_members = read_newc(gzip.decompress(image[offset:offset + reread_size]))
    changed_members = {name for name in set(primary) | set(new_primary)
                       if primary.get(name) != new_primary.get(name)}
    require(not changed_members and new_primary == primary and
            new_boot["kernel"] == boot["kernel"] and
            new_boot["cmdline"] == boot["cmdline"] and
            new_primary["init"]["data"] == changed and
            reread_size == len(payload) and new_members == members,
            "V48 roundtrip or scope check failed")
    OUT.mkdir(mode=0o700)
    target = OUT / "nord3-no-charger-shutdown-v48-untested.img"
    target.write_bytes(image)
    target.chmod(0o600)
    (OUT / "init-before.sh").write_bytes(original)
    (OUT / "init-after.sh").write_bytes(changed)
    (OUT / "health-before.sh").write_bytes(health_before)
    (OUT / "health-after.sh").write_bytes(health_after)
    delta = difflib.unified_diff(original.decode().splitlines(True),
                                 changed.decode().splitlines(True),
                                 fromfile="V47/init", tofile="V48/init")
    (OUT / "init.patch").write_text("".join(delta))
    health_delta = difflib.unified_diff(health_before.decode().splitlines(True),
                                       health_after.decode().splitlines(True),
                                       fromfile="V47/health-start", tofile="V48/health-start")
    (OUT / "health.patch").write_text("".join(health_delta))
    result = {"state": "offline-v48-candidate-built",
              "created_ns": time.time_ns(), "parent_v47_sha256": BASE_SHA,
              "image_sha256": stage.sha(image), "init_sha256": stage.sha(changed),
              "kernel_sha256": stage.sha(boot["kernel"]),
              "ramdisk_bytes": len(ramdisk), "coverage_bytes": coverage,
              "old_payload_sha256": stage.sha(old_payload),
              "new_payload_sha256": stage.sha(payload),
              "health_start_sha256": stage.sha(health_after),
              "changed_primary_members": ["init", "etc/lynx/payload-bytes", "etc/lynx/payload-sha256"],
              "only_changed_supplement_member": HEALTH_MEMBER,
              "tail_after_payload_identical": True,
              "boot_partition_writes": False, "phone_contacted": False,
              "limit": "Offline verification only; hardware boot and charging safety remain unverified."}
    (OUT / "build-result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"state": result["state"], "result": str(OUT / "build-result.json")}))


if __name__ == "__main__":
    main()
