#!/usr/bin/env python3
"""Lynx NFC Tag-Exchange Readiness and Receipt Validator.

Evaluates offline NFC probe receipts and live hardware state for the NXP SN110T
chip on the OnePlus Nord 3 (Lynx).

Critical Distinction Enforced:
- Chip hardware communication (I2C GET_VERSION response) validates driver probe.
- Chip GET_VERSION alone does NOT validate NFC tag exchange.
- Tag exchange requires active RF carrier discovery and successful UID acquisition.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional

PINNED_V53_BOOT_ID = "0fe847d2-44d6-4ac1-9000-2c99df1a51d8"
EXPECTED_MODULES = frozenset({"oplus_nfc", "nfc_i2c"})


def evaluate_nfc_readiness(
    receipt: Dict[str, Any], pinned_boot: str = PINNED_V53_BOOT_ID
) -> Dict[str, Any]:
    """Pure evaluation of an NFC probe or tag trial receipt."""
    reasons: List[str] = []

    # 1. Boot ID check
    boot_id = receipt.get("boot_id", "")
    boot_ok = (boot_id == pinned_boot)
    if not boot_ok and boot_id:
        reasons.append(f"Boot ID mismatch: got '{boot_id}', expected '{pinned_boot}'")

    # 2. Driver Probe Facts
    loaded_mods = set(receipt.get("loaded", []))
    modules_ok = EXPECTED_MODULES.issubset(loaded_mods)
    if not modules_ok:
        reasons.append(f"Missing required modules: {EXPECTED_MODULES - loaded_mods}")

    driver_bound = bool(receipt.get("driver_bound"))
    if not driver_bound:
        reasons.append("Platform driver failed to bind to NFC controller")

    nq_node = bool(receipt.get("nq_node"))
    if not nq_node:
        reasons.append("Device character node /dev/nq-nci was not created")

    watchdog_armed = bool(receipt.get("watchdog_armed"))
    watchdog_cancelled = bool(receipt.get("watchdog_cancelled"))
    if not (watchdog_armed and watchdog_cancelled):
        reasons.append("Watchdog safeguard cycle incomplete (armed: %s, cancelled: %s)" % (
            watchdog_armed, watchdog_cancelled
        ))

    # Probe success check
    state_str = receipt.get("state", "")
    probe_ok = modules_ok and driver_bound and nq_node and watchdog_cancelled and (
        "probe-complete-healthy" in state_str or receipt.get("attempted") == "nfc_i2c"
    )

    # 3. Tag Exchange Facts (RF discovery & UID acquisition)
    tag_exchange = receipt.get("tag_exchange", {})
    tag_detected = bool(tag_exchange.get("tag_detected"))
    tag_uid = tag_exchange.get("tag_uid")
    rf_carrier_active = bool(tag_exchange.get("rf_carrier_active"))

    # 4. Overall Verdict Classification
    if not boot_ok and boot_id:
        verdict = "stale_boot"
    elif not probe_ok:
        verdict = "probe_failed"
    elif tag_detected and tag_uid:
        verdict = "tag_exchange_verified"
        reasons.append(f"Physical NFC tag exchange successful (Tag UID: {tag_uid})")
    else:
        verdict = "driver_verified_tag_pending"
        reasons.append(
            "Driver probe and chip communication verified (GET_VERSION passed), "
            "but physical RF tag exchange has not been executed"
        )

    return {
        "verdict": verdict,
        "boot_id": boot_id,
        "boot_id_matches_pinned": boot_ok,
        "driver_probe": {
            "verified": probe_ok,
            "modules_loaded": sorted(list(loaded_mods)),
            "driver_bound": driver_bound,
            "nq_node_present": nq_node,
            "watchdog_armed": watchdog_armed,
            "watchdog_cancelled": watchdog_cancelled,
        },
        "tag_exchange": {
            "verified": (tag_detected and bool(tag_uid)),
            "tag_detected": tag_detected,
            "tag_uid": tag_uid,
            "rf_carrier_active": rf_carrier_active,
        },
        "limits": [
            "GET_VERSION chip response proves I2C bus wiring and controller boot, but NOT RF field modulation",
            "NFC is NOT validated until an actual physical tag is read during an attended trial",
            "No Android NFC HAL daemon is installed on native Alpine Linux",
        ],
        "reasons": reasons,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Lynx NFC Readiness and Receipt Validator")
    parser.add_argument("receipt", type=str, help="Path to NFC receipt JSON file")
    parser.add_argument("--pinned-boot", type=str, default=PINNED_V53_BOOT_ID, help="Expected pinned boot ID")
    parser.add_argument("--text", action="store_true", help="Output human-readable text summary")
    args = parser.parse_args()

    receipt_path = Path(args.receipt)
    if not receipt_path.is_file():
        print(f"Error: Receipt file not found at {receipt_path}", file=sys.stderr)
        sys.exit(2)

    with open(receipt_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    result = evaluate_nfc_readiness(data, pinned_boot=args.pinned_boot)

    if args.text:
        print(f"NFC Readiness Verdict: {result['verdict'].upper()}")
        print(f"Boot ID: {result['boot_id']} (matches pinned: {result['boot_id_matches_pinned']})")
        print("\nSubsystem Status:")
        dp = result["driver_probe"]
        te = result["tag_exchange"]
        print(f"  Driver Probe:  {'VERIFIED' if dp['verified'] else 'FAILED'} (node: {dp['nq_node_present']}, bound: {dp['driver_bound']})")
        print(f"  Tag Exchange:  {'VERIFIED' if te['verified'] else 'PENDING'} (detected: {te['tag_detected']}, uid: {te['tag_uid']})")
        print("\nFindings:")
        for r in result["reasons"]:
            print(f"  - {r}")
        print("\nEnforced Operating Limits:")
        for lim in result["limits"]:
            print(f"  - {lim}")
    else:
        print(json.dumps(result, indent=2))

    if result["verdict"] == "tag_exchange_verified":
        sys.exit(0)
    elif result["verdict"] == "driver_verified_tag_pending":
        sys.exit(1)
    else:
        sys.exit(3)


if __name__ == "__main__":
    main()
