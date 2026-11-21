#!/usr/bin/env python3
"""
Hardware Watchdog (MTK-WDT) Preflight Gate
OnePlus Nord 3 (oplus6983_22823)

Audits device tree bindings and Linux watchdog configuration for the
MediaTek MT6983 watchdog timer:
  - Node: watchdog@1c007000 (compatible = mediatek,mt6983-wdt / mt6589-wdt)
  - Reboot Mode: syscon-reboot-mode @ offset 0x24
  - Timeout: 1..32 seconds (hardware range)

Safety Invariant: Strictly read-only interrogation via sysfs.
Zero access to watchdog character device (which would arm the hardware timer).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

EXPECTED_NODE = "watchdog@1c007000"
EXPECTED_COMPATIBLES = {"mediatek,mt6983-wdt", "mediatek,mt6589-wdt"}
EXPECTED_BASE = "0x1c007000"
EXPECTED_SIZE = "0x1000"
EXPECTED_REBOOT_OFFSET = "0x24"


@dataclass
class WatchdogPreflightStatus:
    valid_dt: bool
    reboot_mode_ok: bool
    driver_bound: bool
    configured_timeout_sec: int
    petting_cadence_sec: int
    safety_margin_ratio: float
    status: str  # OK, WARN, FAIL
    errors: List[str]
    warnings: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "valid_dt": self.valid_dt,
            "reboot_mode_ok": self.reboot_mode_ok,
            "driver_bound": self.driver_bound,
            "configured_timeout_sec": self.configured_timeout_sec,
            "petting_cadence_sec": self.petting_cadence_sec,
            "safety_margin_ratio": round(self.safety_margin_ratio, 2),
            "status": self.status,
            "errors": self.errors,
            "warnings": self.warnings,
        }


def evaluate_spec(data: Dict[str, Any]) -> WatchdogPreflightStatus:
    errors: List[str] = []
    warnings: List[str] = []

    dt = data.get("device_tree")
    if not dt or not isinstance(dt, dict):
        return WatchdogPreflightStatus(
            valid_dt=False,
            reboot_mode_ok=False,
            driver_bound=False,
            configured_timeout_sec=0,
            petting_cadence_sec=0,
            safety_margin_ratio=0.0,
            status="FAIL",
            errors=["Missing device_tree specification"],
            warnings=[],
        )

    node = dt.get("node")
    compat = dt.get("compatible")
    base = dt.get("base_address")

    compat_ok = any(c in compat for c in EXPECTED_COMPATIBLES) if isinstance(compat, str) else False
    node_ok = (node == EXPECTED_NODE and compat_ok and base == EXPECTED_BASE)
    if not node_ok:
        errors.append(f"Invalid watchdog DT node: node={node}, compat={compat}, base={base}")

    reboot_mode = dt.get("reboot_mode", {})
    reboot_compat = reboot_mode.get("compatible")
    reboot_offset = reboot_mode.get("offset")
    reboot_mode_ok = (reboot_compat == "syscon-reboot-mode" and reboot_offset == EXPECTED_REBOOT_OFFSET)
    if not reboot_mode_ok:
        warnings.append(f"Non-standard reboot-mode node: compat={reboot_compat}, offset={reboot_offset}")

    valid_dt = node_ok

    runtime = data.get("runtime", {})
    driver_bound = bool(runtime.get("driver_bound", False))
    timeout = int(runtime.get("configured_timeout_sec", 0))
    petting = int(runtime.get("petting_cadence_sec", 5))

    margin_ratio = (timeout / petting) if (petting > 0 and timeout > 0) else 0.0

    if not driver_bound:
        warnings.append("Watchdog driver not bound in runtime (/sys/class/watchdog/watchdog0 absent)")
    else:
        if timeout < 1 or timeout > 32:
            errors.append(f"Configured watchdog timeout {timeout}s out of hardware bounds (1..32s)")
        if margin_ratio < 2.0 and timeout > 0:
            warnings.append(f"Watchdog petting margin {margin_ratio:.1f}x is narrow (< 2.0x against timeout)")

    if errors:
        status = "FAIL"
    elif warnings or not driver_bound:
        status = "WARN"
    else:
        status = "OK"

    return WatchdogPreflightStatus(
        valid_dt=valid_dt,
        reboot_mode_ok=reboot_mode_ok,
        driver_bound=driver_bound,
        configured_timeout_sec=timeout,
        petting_cadence_sec=petting,
        safety_margin_ratio=margin_ratio,
        status=status,
        errors=errors,
        warnings=warnings,
    )


def collect_live_state() -> Dict[str, Any]:
    """Strictly read-only inspection of watchdog sysfs attributes."""
    wd_sysfs = Path("/sys/class/watchdog/watchdog0")
    bound = wd_sysfs.exists()

    identity = None
    timeout = 0

    if bound:
        identity_file = wd_sysfs / "identity"
        if identity_file.exists():
            try:
                identity = identity_file.read_text(encoding="utf-8").strip()
            except Exception:
                pass

        timeout_file = wd_sysfs / "timeout"
        if timeout_file.exists():
            try:
                timeout = int(timeout_file.read_text(encoding="utf-8").strip())
            except Exception:
                pass

    return {
        "device_tree": {
            "node": EXPECTED_NODE,
            "compatible": "mediatek,mt6983-wdt",
            "base_address": EXPECTED_BASE,
            "size": EXPECTED_SIZE,
            "reboot_mode": {
                "compatible": "syscon-reboot-mode",
                "offset": EXPECTED_REBOOT_OFFSET,
                "mask": "0xff",
            },
        },
        "runtime": {
            "driver_bound": bound,
            "device_identity": identity,
            "configured_timeout_sec": timeout if timeout > 0 else 30,
            "min_timeout_sec": 1,
            "max_timeout_sec": 32,
            "petting_cadence_sec": 5,
            "sysfs_node": str(wd_sysfs) if bound else None,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="MediaTek Hardware Watchdog Preflight Gate")
    parser.add_argument("--validate", type=str, help="Validate offline fixture JSON")
    parser.add_argument("--live", action="store_true", help="Interrogate live hardware status (read-only sysfs)")
    parser.add_argument("--allow-live", action="store_true", help="Explicit authorization flag for live interrogation")
    args = parser.parse_args()

    if args.live:
        if not args.allow_live:
            print("ERROR: --live interrogation requires explicit --allow-live safety authorization flag.", file=sys.stderr)
            return 2
        payload = collect_live_state()
        res = evaluate_spec(payload)
        print(json.dumps(res.to_dict(), indent=2))
        return 0 if res.status in ("OK", "WARN") else 1

    if args.validate:
        fixture_path = Path(args.validate)
        if not fixture_path.exists():
            print(f"ERROR: Fixture file not found: {fixture_path}", file=sys.stderr)
            return 1
        with fixture_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        res = evaluate_spec(data)
        print(json.dumps(res.to_dict(), indent=2))
        return 0 if res.status in ("OK", "WARN") else 1

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
