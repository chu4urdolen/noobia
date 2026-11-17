#!/usr/bin/env python3
"""Independent offline check of Lynx V48 against exact V47 and stock boot."""

import hashlib
import gzip
import json
from pathlib import Path
import re
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parent.parent
PORT = ROOT / "linux-port"
OLD_DIR = PORT / "artifacts/wifi-dhcp-retry-v47-offline"
NEW_DIR = PORT / "artifacts/no-charger-shutdown-v48-offline"
OLD = OLD_DIR / "nord3-wifi-dhcp-retry-v47-untested.img"
NEW = NEW_DIR / "nord3-no-charger-shutdown-v48-untested.img"
STOCK_DIR = PORT / "artifacts/stock-cph2493-August-eu-ota"
STOCK = STOCK_DIR / "boot.img"
MODEL = ROOT / "tools/avb-host/avb-boot-model"
OLD_SHA = "c969e1938b051ab03b49ad4f2260e900e9e336997d1026ca00c3a493dedde066"
OLD_INIT_SHA = "ebc6bb746aaf710d915c47036f92ce0c4ed23a185dfb5349b90e654bab7ba4ae"
sys.path.insert(0, str(PORT))
from image_formats import read_boot_v4, read_newc  # noqa: E402
from ramdisk_codec import decompress  # noqa: E402


def sha(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def main():
    old, new, stock = OLD.read_bytes(), NEW.read_bytes(), STOCK.read_bytes()
    build = json.loads((NEW_DIR / "build-result.json").read_text())
    require(len(old) == len(new) == 67_108_864, "unexpected image size")
    require(sha(old) == OLD_SHA == build["parent_v47_sha256"], "V47 hash mismatch")
    require(sha(new) == build["image_sha256"], "V48 hash mismatch")
    require(build["state"] == "offline-v48-candidate-built", "build state mismatch")
    old_boot, new_boot, stock_boot = map(read_boot_v4, (old, new, stock))
    require(new_boot["kernel"] == old_boot["kernel"] == stock_boot["kernel"],
            "stock kernel changed")
    require(new_boot["cmdline"] == old_boot["cmdline"], "boot command line changed")
    old_files = read_newc(decompress(old_boot["ramdisk"]))
    new_files = read_newc(decompress(new_boot["ramdisk"]))
    changed = {name for name in set(old_files) | set(new_files)
               if old_files.get(name) != new_files.get(name)}
    require(changed == {"init", "etc/lynx/payload-bytes", "etc/lynx/payload-sha256"},
            f"primary changes: {sorted(changed)}")
    before, after = old_files["init"]["data"], new_files["init"]["data"]
    require(sha(before) == OLD_INIT_SHA and sha(after) == build["init_sha256"],
            "init receipt mismatch")
    require((NEW_DIR / "init-before.sh").read_bytes() == before and
            (NEW_DIR / "init-after.sh").read_bytes() == after, "review sources mismatch")
    require(before.count(b"V41_CHARGER_ONLINE; POWER_OFF_REQUESTED") == 1 and
            before.count(b"V41_CHARGER_GUARD_POWER_OFF") == 1 and
            b"V41_CHARGER_ONLINE; POWER_OFF_REQUESTED" not in after and
            b"V41_CHARGER_GUARD_POWER_OFF" not in after and
            b"v40_charger_guard" not in after, "charger guard delta mismatch")
    # Remove both exact diff hunks from the old init, then compare every byte.
    first = re.compile(rb"    v40_supplies=0\n.*?    \$BB sleep 5\n", re.S)
    second = re.compile(rb"\(\n    while :; do\n        v40_guard_count=0\n.*?v40-charger-guard\.pid \|\| stop\n", re.S)
    require(len(first.findall(before)) == len(second.findall(before)) == 1,
            "charger blocks not unique")
    expected = first.sub(b"    # V48: permit powered boot; thermal and battery watchers remain active.\n    $BB sleep 5\n", before)
    expected = second.sub(b"log 'V48_CHARGER_SHUTDOWN_REMOVED; HEALTH_WATCHERS_ACTIVE'\n", expected)
    require(expected == after, "unexpected init delta")
    require(b"lynx_autonomous_health_local_handoff" in after and
            b"lynx_persistent_openrc_handoff" in after, "health handoff changed")
    syntax = subprocess.run(["busybox", "sh", "-n"], input=after,
                            capture_output=True, timeout=20)
    require(syntax.returncode == 0, "shell syntax invalid")
    recipe = json.loads((PORT / "known-good-v19/recipe.json").read_text())
    offset = recipe["payload_offset"]
    old_size = int(old_files["etc/lynx/payload-bytes"]["data"].strip())
    new_size = int(new_files["etc/lynx/payload-bytes"]["data"].strip())
    old_payload = old[offset:offset + old_size]
    new_payload = new[offset:offset + new_size]
    require(sha(old_payload) == old_files["etc/lynx/payload-sha256"]["data"].strip().decode() ==
            build["old_payload_sha256"], "V47 payload checksum mismatch")
    require(sha(new_payload) == new_files["etc/lynx/payload-sha256"]["data"].strip().decode() ==
            build["new_payload_sha256"], "V48 payload checksum mismatch")
    old_pack = read_newc(gzip.decompress(old_payload))
    new_pack = read_newc(gzip.decompress(new_payload))
    supplement_changed = {name for name in set(old_pack) | set(new_pack)
                          if old_pack.get(name) != new_pack.get(name)}
    member = "usr/libexec/lynx/autonomous-health-start.sh"
    require(supplement_changed == {member}, f"supplement changes: {sorted(supplement_changed)}")
    health_before = old_pack[member]["data"]
    health_after = new_pack[member]["data"]
    health_old = (b"        offline_supplies=0\n        for supply in /sys/class/power_supply/*; do\n"
                  b"            [ -r \"$supply/online\" ] || continue\n"
                  b"            online=$(cat \"$supply/online\") || fail 'charger state unreadable'\n"
                  b"            [ \"$online\" = 0 ] || fail 'USB or charger is online; charging unvalidated'\n"
                  b"            offline_supplies=$((offline_supplies+1))\n"
                  b"        done\n"
                  b"        [ \"$offline_supplies\" -ge 1 ] || fail 'no charger state available';;\n")
    require(health_before.count(health_old) == 1 and
            health_before.replace(health_old, b"        say 'V48_CHARGER_BOOT_ALLOWED';;\n") == health_after,
            "health startup delta mismatch")
    require((NEW_DIR / "health-before.sh").read_bytes() == health_before and
            (NEW_DIR / "health-after.sh").read_bytes() == health_after and
            sha(health_after) == build["health_start_sha256"], "health review source mismatch")
    require(subprocess.run(["busybox", "sh", "-n"], input=health_after,
                           capture_output=True, timeout=20).returncode == 0,
            "health shell syntax invalid")
    end = offset + max(old_size, new_size)
    require(new[end:] == old[end:], "image tail after payload changed")
    reference = json.loads((PORT / "docs/avb-boot-model-results.json").read_text())
    require(sha(MODEL.read_bytes()) == reference["binary_sha256"], "AVB model changed")
    cases = []
    for unlocked in (1, 0):
        check = subprocess.run([str(MODEL), str(STOCK_DIR), str(NEW), "0", str(unlocked)],
                               capture_output=True, timeout=30)
        require(check.returncode == 0, "AVB model failed")
        cases.append(json.loads(check.stdout))
    require(cases[0]["slot_data_returned"] and cases[0]["boot_partitions_loaded"] == 1 and
            not cases[1]["slot_data_returned"] and cases[1]["boot_partitions_loaded"] == 0,
            "AVB model behavior changed")
    result = {"state": "offline-v48-validation-passed", "created_ns": time.time_ns(),
              "image_sha256": sha(new), "rollback_v47_sha256": sha(old),
              "changed_primary_members": sorted(changed), "tail_after_payload_identical": True,
              "changed_supplement_members": sorted(supplement_changed),
              "avb_cases": cases, "phone_contacted": False, "flash_performed": False,
              "limit": "Offline checks cannot prove hardware charging, thermal response or autonomous boot."}
    (NEW_DIR / "validation.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"state": result["state"], "result": str(NEW_DIR / "validation.json")}))


if __name__ == "__main__":
    main()
