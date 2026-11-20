#!/usr/bin/env python3
"""Lynx Modem (CCCI) Preflight Gate Tool.

Strict read-only preflight validator for the MediaTek MT6983 cellular modem
subsystem (MD1) on OnePlus Nord 3 running native Alpine Linux.

Enforces Noob and Aria safety gates:
- Strict no-write default (no sysfs writes, no character device opens, no module loads).
- Asserts SIM card is physically removed / unbound.
- Asserts current CCCI state is baseline md1:0 (INVALID).
- Verifies local stock artifacts (ccci_mdinit, md1img) on Nexus.
- Validates battery (>=50%) and thermal health.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple

PINNED_BOOT_ID = "0fe847d2-44d6-4ac1-9000-2c99df1a51d8"
EXPECTED_KERNEL = "5.10.149-android12-9-o-g311738fbb5a8"
MIN_BATTERY_PERCENT = 50
MAX_TEMP_MC = 45000  # 45 deg C

STOCK_MDINIT_PATH = "/noobia/lynx/linux-port/artifacts/stock-cph2493-August-eu-ota/wifi-reference/vendor-unpacked/bin/ccci_mdinit"
STOCK_MDINIT_SHA256 = "a288eb339fbc13c7a1c135855dbd2de94b01fadc93059ec4e9f5075528582849"

PARTITIONS_JSON_PATH = "/noobia/lynx/linux-port/artifacts/stock-cph2493-August-eu-ota/payload-partitions.json"
EXPECTED_MD1IMG_SHA256 = "7cf648e726d4ef57e9e82eb918c113156c73f0f4118f1011973c022af10c2fa7"

CRITICAL_CCCI_DEV_NODES = [
    "/dev/ccci_ioctl0",
    "/dev/ccci_ioctl1",
    "/dev/ccci_ioctl2",
    "/dev/ccci_ioctl3",
    "/dev/ccci_ioctl4",
    "/dev/ccci_md1_sta",
    "/dev/ccci_fs",
    "/dev/ccci_rpc",
    "/dev/ttyC0",
]


def sha256_file(path: str) -> Optional[str]:
    """Compute SHA-256 of a local file."""
    if not os.path.isfile(path):
        return None
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def check_stock_artifacts(
    mdinit_path: str = STOCK_MDINIT_PATH,
    partitions_path: str = PARTITIONS_JSON_PATH,
) -> Tuple[bool, List[str], Dict[str, Any]]:
    """Verify stock ccci_mdinit and md1img partition metadata on Nexus."""
    blockers: List[str] = []
    details: Dict[str, Any] = {}

    # Check ccci_mdinit
    actual_mdinit_hash = sha256_file(mdinit_path)
    if actual_mdinit_hash is None:
        blockers.append(f"Stock ccci_mdinit missing at {mdinit_path}")
    elif actual_mdinit_hash != STOCK_MDINIT_SHA256:
        blockers.append(
            f"Stock ccci_mdinit SHA-256 mismatch: got {actual_mdinit_hash}, expected {STOCK_MDINIT_SHA256}"
        )
    details["ccci_mdinit_sha256"] = actual_mdinit_hash

    # Check payload-partitions.json for md1img
    if not os.path.isfile(partitions_path):
        blockers.append(f"Partitions manifest missing at {partitions_path}")
    else:
        try:
            with open(partitions_path, "r", encoding="utf-8") as f:
                parts = json.load(f)
            md1 = parts.get("md1img", {})
            md1_hash = md1.get("sha256")
            if md1_hash != EXPECTED_MD1IMG_SHA256:
                blockers.append(
                    f"Stock md1img partition hash mismatch: got {md1_hash}, expected {EXPECTED_MD1IMG_SHA256}"
                )
            details["md1img_sha256"] = md1_hash
            details["md1img_size"] = md1.get("size")
        except Exception as e:
            blockers.append(f"Failed parsing partitions manifest: {e}")

    return len(blockers) == 0, blockers, details


def evaluate_preflight(
    status_data: Dict[str, Any],
    ccci_boot_str: Optional[str],
    present_dev_nodes: List[str],
    sim_nodes_unbound: bool,
    stock_ok: bool,
    stock_blockers: List[str],
    stock_details: Dict[str, Any],
    pinned_boot: str = PINNED_BOOT_ID,
) -> Dict[str, Any]:
    """Evaluate preflight readiness from collected data."""
    blockers: List[str] = []
    blockers.extend(stock_blockers)

    # Boot ID check
    boot_id = status_data.get("boot_id", "")
    if boot_id != pinned_boot:
        blockers.append(f"Boot ID mismatch: got '{boot_id}', expected '{pinned_boot}'")

    # Battery check
    bat = status_data.get("battery", {})
    cap = bat.get("capacity_percent", 0)
    if cap < MIN_BATTERY_PERCENT:
        blockers.append(f"Battery too low: {cap}% < {MIN_BATTERY_PERCENT}%")

    # Thermal check
    thermal = status_data.get("thermal", {})
    max_mC = thermal.get("max_mC", 0)
    if max_mC > MAX_TEMP_MC:
        blockers.append(f"SoC thermal too high: {max_mC / 1000:.1f}C > {MAX_TEMP_MC / 1000:.1f}C")

    # SIM unbound check
    if not sim_nodes_unbound:
        blockers.append("SIM platform device nodes appear to have a bound driver (SIM must be out/unbound)")

    # CCCI device nodes check
    missing_nodes = [node for node in CRITICAL_CCCI_DEV_NODES if node not in present_dev_nodes]
    if missing_nodes:
        blockers.append(f"Missing critical CCCI device nodes: {missing_nodes}")

    # CCCI baseline state check
    # /sys/kernel/ccci/boot should report md1:0 (INVALID)
    if ccci_boot_str is None:
        blockers.append("/sys/kernel/ccci/boot could not be read")
    elif "md1:0" not in ccci_boot_str:
        blockers.append(f"Modem MD1 is not in baseline state md1:0 (got: '{ccci_boot_str.strip()}')")

    state = "ready" if not blockers else "blocked"
    return {
        "state": state,
        "blockers": blockers,
        "evidence": {
            "boot_id": boot_id,
            "battery_percent": cap,
            "max_temp_mC": max_mC,
            "sim_nodes_unbound": sim_nodes_unbound,
            "ccci_boot": ccci_boot_str.strip() if ccci_boot_str else None,
            "missing_ccci_nodes": missing_nodes,
            "stock_artifacts": stock_details,
        },
    }


def collect_live_state(
    host: str = "192.168.100.107", port: int = 2222
) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str], List[str], bool, str]:
    """Collect live telemetry from Lynx over read-only SSH."""
    # 1. Run lynx-status --assert-ready
    status_cmd = [
        "ssh",
        "-p",
        str(port),
        f"root@{host}",
        "/usr/local/bin/lynx-status --assert-ready",
    ]
    try:
        res = subprocess.run(status_cmd, capture_output=True, text=True, timeout=10)
        if res.returncode != 0:
            return False, None, None, [], False, f"lynx-status failed: {res.stderr}"
        status_data = json.loads(res.stdout)
    except Exception as e:
        return False, None, None, [], False, f"Failed collecting lynx-status: {e}"

    # 2. Check /sys/kernel/ccci/boot and dev nodes
    collector_sh = r"""
cat /sys/kernel/ccci/boot 2>/dev/null || echo "MISSING_CCCI_BOOT"
echo "===DEV==="
ls -1 /dev/ccci_* /dev/ttyC* 2>/dev/null
echo "===SIM==="
for p in /sys/devices/platform/*SIM* /sys/devices/platform/odm:oplus_sim_detect; do
    if [ -d "$p/driver" ]; then echo "BOUND:$p"; fi
done
"""
    probe_cmd = ["ssh", "-p", str(port), f"root@{host}", "sh", "-s"]
    try:
        res = subprocess.run(probe_cmd, input=collector_sh, capture_output=True, text=True, timeout=10)
        if res.returncode != 0:
            return False, status_data, None, [], False, f"Collector probe failed: {res.stderr}"
        parts = res.stdout.split("===DEV===")
        boot_str = parts[0].strip()
        rest = parts[1].split("===SIM===") if len(parts) > 1 else ["", ""]
        dev_nodes = [line.strip() for line in rest[0].splitlines() if line.strip()]
        sim_out = rest[1].strip() if len(rest) > 1 else ""
        sim_unbound = "BOUND:" not in sim_out
        return True, status_data, boot_str, dev_nodes, sim_unbound, "OK"
    except Exception as e:
        return False, status_data, None, [], False, f"Collector script failed: {e}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Lynx Modem Preflight Gate")
    parser.add_argument("--live", action="store_true", help="Perform live check against Lynx")
    parser.add_argument("--allow-live", action="store_true", help="Explicit confirmation for live SSH read")
    parser.add_argument("--json", action="store_true", help="Output results in JSON format")
    parser.add_argument("--host", default="192.168.100.107", help="Lynx SSH IP")
    parser.add_argument("-p", "--port", type=int, default=2222, help="Lynx SSH port")
    args = parser.parse_args()

    # 1. Always verify stock artifacts on Nexus
    stock_ok, stock_blockers, stock_details = check_stock_artifacts()

    if not args.live:
        # Offline mode: stock artifact validation only
        res = {
            "mode": "offline",
            "state": "ready" if stock_ok else "blocked",
            "blockers": stock_blockers,
            "stock_artifacts": stock_details,
        }
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            print(f"Modem Preflight (Offline): {res['state'].upper()}")
            for b in stock_blockers:
                print(f"  BLOCKER: {b}")
        return 0 if stock_ok else 1

    if not args.allow_live:
        err = {"state": "blocked", "blockers": ["Live check requires explicit --allow-live flag"]}
        if args.json:
            print(json.dumps(err, indent=2))
        else:
            print("ERROR: Live check requires explicit --allow-live flag")
        return 1

    ok, status_data, boot_str, dev_nodes, sim_unbound, err_msg = collect_live_state(
        host=args.host, port=args.port
    )
    if not ok or status_data is None:
        res = {"state": "blocked", "blockers": [f"Live collection failed: {err_msg}"]}
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            print(f"ERROR: {err_msg}")
        return 1

    eval_result = evaluate_preflight(
        status_data=status_data,
        ccci_boot_str=boot_str,
        present_dev_nodes=dev_nodes,
        sim_nodes_unbound=sim_unbound,
        stock_ok=stock_ok,
        stock_blockers=stock_blockers,
        stock_details=stock_details,
    )

    if args.json:
        print(json.dumps(eval_result, indent=2))
    else:
        print(f"Modem Preflight (Live): {eval_result['state'].upper()}")
        for b in eval_result["blockers"]:
            print(f"  BLOCKER: {b}")
        if eval_result["state"] == "ready":
            print("  All preflight gates passed cleanly. No live writes were performed.")

    return 0 if eval_result["state"] == "ready" else 1


if __name__ == "__main__":
    sys.exit(main())
