#!/usr/bin/env python3
"""Guarded online ext4 growth on Lynx's existing userdata partition.

Only /dev/sdc85 filesystem metadata is changed. No GPT, boot, or slot writes.
Use --preflight first; --grow repeats every gate and runs resize2fs once.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time

from backup_full_ufs import PHONE, PHONE_SERIAL, V53_BOOT_SHA256, health
from lynx_wifi_v19_contact import ssh_command
from validate_alpine_backup import validate_receipt


ROOT = Path(__file__).resolve().parent.parent
ARCHIVE = ROOT / "backups/alpine-files-20261107-v53/alpine-files.tar.gz"
RECEIPT = ROOT / "backups/alpine-files-20261107-v53/alpine-files.json"
V53 = ROOT / "linux-port/artifacts/bt-precal-settle-v53-offline/nord3-bt-precal-settle-v53-untested.img"
V50 = ROOT / "linux-port/artifacts/static-noobia-ip-v50-offline/nord3-static-noobia-ip-v50-untested.img"
V50_SHA256 = "6168cd6288679a321a4d8bc41c7d3dde64a49d3cfe855b8e44542f3307fd5a59"
PART_START = 33_783_808
PART_SECTORS = 466_026_432
PART_BLOCKS = PART_SECTORS // 8
OLD_BLOCKS = 262_144
UUID = "13dc3665-b062-405e-b674-ceae8972fc0f"
GPT_PREFIX_SHA256 = "f670f42df898d287515c89730661ac8dde238be8f1712d1d00b549551f987d4b"
OUT = ROOT / "logs/root-grow-20261107"


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def remote(command, timeout=30, name=None):
    argv = ssh_command(PHONE, command)
    argv[-2:-2] = ["-p", "2222", "-T", "-o", "ServerAliveInterval=10",
                    "-o", "ServerAliveCountMax=3"]
    run = subprocess.run(argv, capture_output=True, timeout=timeout)
    if name:
        (OUT / f"{name}.stdout").write_bytes(run.stdout)
        (OUT / f"{name}.stderr").write_bytes(run.stderr)
    if run.returncode:
        raise RuntimeError(f"remote {name or 'check'} failed: exit {run.returncode}")
    return run.stdout.decode(errors="replace")


def field(report, label):
    match = re.search(rf"^{re.escape(label)}:\s*(.+)$", report, re.MULTILINE)
    if not match:
        raise RuntimeError(f"missing tune2fs field: {label}")
    return match.group(1).strip()


def snapshot():
    status = health()
    command = ("set -eu; cat /proc/sys/kernel/random/boot_id; "
               "sed -n 's/.*oplusboot.serialno=\\([^ ]*\\).*/\\1/p' /proc/cmdline; "
               "sha256sum /dev/sdc39 | cut -c1-64; "
               "cat /sys/class/block/sdc85/start /sys/class/block/sdc85/size; "
               "dd if=/dev/sdc bs=1048576 count=4 2>/dev/null | sha256sum | cut -c1-64; "
               "/usr/sbin/tune2fs -l /dev/sdc85")
    lines = remote(command, name="identity-and-ext4").splitlines()
    if len(lines) < 7:
        raise RuntimeError("incomplete remote filesystem inventory")
    boot_id, serial, boot_sha, start, sectors, gpt_sha = lines[:6]
    tune = "\n".join(lines[6:])
    result = {"status": status, "boot_id": boot_id, "serial": serial,
              "boot_sha256": boot_sha, "start_sector": int(start),
              "partition_sectors": int(sectors), "gpt_prefix_sha256": gpt_sha,
              "label": field(tune, "Filesystem volume name"),
              "uuid": field(tune, "Filesystem UUID"),
              "state": field(tune, "Filesystem state"),
              "features": field(tune, "Filesystem features").split(),
              "block_count": int(field(tune, "Block count")),
              "block_size": int(field(tune, "Block size"))}
    return result


def preflight(allow_charging_low_battery=False):
    archive_receipt = validate_receipt(ARCHIVE, RECEIPT)
    if archive_receipt["device_serial"] != PHONE_SERIAL or archive_receipt["boot_sha256"] != V53_BOOT_SHA256:
        raise RuntimeError("file archive identity mismatch")
    if V53.stat().st_size != 67_108_864 or sha(V53) != V53_BOOT_SHA256:
        raise RuntimeError("V53 boot image missing or changed")
    if V50.stat().st_size != 67_108_864 or sha(V50) != V50_SHA256:
        raise RuntimeError("V50 rollback image missing or changed")
    current = snapshot()
    status = current["status"]
    battery = status["battery"]
    if status["boot_id"] != current["boot_id"] or status["issues"]:
        raise RuntimeError("Lynx boot or health changed")
    if battery["capacity_percent"] < 45:
        if not allow_charging_low_battery or battery["capacity_percent"] < 25 or battery["current_mA_signed"] < 100:
            raise RuntimeError("battery gate failed")
        charger = remote("cat /sys/class/power_supply/11e01000.i2c:mt6375@34:chg/status").strip()
        if charger != "Charging":
            raise RuntimeError("low-battery charging override lost external power")
        current["charging_override"] = {"charger_status": charger,
                                         "minimum_capacity_percent": 25,
                                         "minimum_current_mA_signed": 100}
    if battery["temperature_mC"] >= 35_000:
        raise RuntimeError("battery gate failed")
    if status["thermal"]["max_mC"] >= 50_000:
        raise RuntimeError("thermal gate failed")
    if status["root_filesystem"]["source"] != "/dev/sdc85" or status["root_filesystem"]["type"] != "ext4":
        raise RuntimeError("unexpected root mount")
    if (current["serial"] != PHONE_SERIAL or current["boot_sha256"] != V53_BOOT_SHA256 or
            current["start_sector"] != PART_START or current["partition_sectors"] != PART_SECTORS or
            current["gpt_prefix_sha256"] != GPT_PREFIX_SHA256 or
            current["label"] != "LYNXROOT" or current["uuid"] != UUID or
            current["block_count"] != OLD_BLOCKS or current["block_size"] != 4096 or
            current["state"] != "clean"):
        raise RuntimeError("filesystem or partition preflight mismatch")
    if not {"resize_inode", "64bit", "extent", "has_journal"}.issubset(current["features"]):
        raise RuntimeError("required ext4 features missing")
    if status["root_free_mib"] < 300:
        raise RuntimeError("Alpine root space too low for resize tool")
    return current


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preflight", action="store_true")
    mode.add_argument("--grow", action="store_true")
    parser.add_argument("--allow-charging-low-battery", action="store_true",
                        help="Explicitly permit growth at >=25%% only while external charging is confirmed")
    args = parser.parse_args()
    if args.allow_charging_low_battery and not args.grow:
        parser.error("charging override is only valid with --grow")
    os.umask(0o077)
    OUT.mkdir(parents=True, exist_ok=True, mode=0o700)
    record = {"mode": "grow" if args.grow else "preflight", "state": "started",
              "started_ns": time.time_ns(), "partition_table_writes": False,
              "boot_partition_writes": False}
    try:
        before = preflight(args.allow_charging_low_battery)
        record["before"] = before
        if args.grow:
            record["command"] = "/usr/sbin/resize2fs /dev/sdc85"
            (OUT / "resize-started.json").write_text(json.dumps({"boot_id": before["boot_id"],
                "command": record["command"], "started_ns": time.time_ns()}) + "\n")
            remote(record["command"], timeout=900, name="resize")
            remote("/bin/busybox sync", timeout=60, name="sync")
            after = snapshot()
            record["after"] = after
            if (after["boot_id"] != before["boot_id"] or
                    after["start_sector"] != PART_START or after["partition_sectors"] != PART_SECTORS or
                    after["gpt_prefix_sha256"] != GPT_PREFIX_SHA256 or
                    after["uuid"] != UUID or after["block_size"] != 4096 or
                    after["block_count"] < PART_BLOCKS * 95 // 100 or
                    after["block_count"] > PART_BLOCKS or after["status"]["issues"]):
                raise RuntimeError("post-resize identity, size, or health verification failed")
            record["state"] = "grown-and-verified"
        else:
            record["state"] = "preflight-passed"
    except Exception as error:
        record.update(state="stopped", error=str(error))
    finally:
        record["finished_ns"] = time.time_ns()
        (OUT / "result.json").write_text(json.dumps(record, indent=2) + "\n")
        print(json.dumps({"state": record["state"], "result": str(OUT / "result.json"),
                          "error": record.get("error")}))
    return 0 if record["state"] in {"preflight-passed", "grown-and-verified"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
