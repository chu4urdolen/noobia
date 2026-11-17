#!/usr/bin/env python3
"""Independently check a completed Lynx ext4 growth receipt, without device I/O."""

import argparse
import json
from pathlib import Path


IDENTITY = ("serial", "boot_sha256", "boot_id", "start_sector",
            "partition_sectors", "gpt_prefix_sha256", "uuid", "block_size")
EXPECTED = {
    "serial": "89BYAY5L4T9HFUOV",
    "boot_sha256": "c047455271828cf9bfa90984eea121d8ede8754f6297fc06f33f1e99fb23c75e",
    "start_sector": 33_783_808,
    "partition_sectors": 466_026_432,
    "gpt_prefix_sha256": "f670f42df898d287515c89730661ac8dde238be8f1712d1d00b549551f987d4b",
    "uuid": "13dc3665-b062-405e-b674-ceae8972fc0f",
    "block_size": 4096,
}


def audit(data):
    if not isinstance(data, dict) or data.get("state") != "grown-and-verified":
        raise ValueError("receipt is not a completed growth")
    before, after = data.get("before"), data.get("after")
    if not isinstance(before, dict) or not isinstance(after, dict):
        raise ValueError("missing filesystem snapshots")
    for field in IDENTITY:
        if field not in before or field not in after or before[field] != after[field]:
            raise ValueError(f"missing or changed {field}")
        if field in EXPECTED and before[field] != EXPECTED[field]:
            raise ValueError(f"unexpected {field}")
    if not isinstance(before["boot_id"], str) or not before["boot_id"]:
        raise ValueError("invalid boot ID")
    old, new = before.get("block_count"), after.get("block_count")
    if type(old) is not int or type(new) is not int or old != 262_144:
        raise ValueError("invalid filesystem block counts")
    capacity = EXPECTED["partition_sectors"] // 8
    if not (old < new <= capacity and new >= capacity * 95 // 100):
        raise ValueError("filesystem did not grow to partition capacity")
    status = after.get("status")
    if not isinstance(status, dict) or status.get("issues") != []:
        raise ValueError("missing or unhealthy post-growth status")
    if after.get("state") != "clean" or after.get("label") != "LYNXROOT":
        raise ValueError("filesystem state or label changed")
    return {"status": "pass", "old_blocks": old, "new_blocks": new}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipt", type=Path)
    args = parser.parse_args()
    try:
        result = audit(json.loads(args.receipt.read_text()))
    except (OSError, ValueError, TypeError) as exc:
        print(json.dumps({"status": "fail", "reason": str(exc)}))
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
