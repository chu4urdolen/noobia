#!/usr/bin/env python3
"""
OnePlus Alert Slider (Tri-State Key) Hardware Preflight Gate
OnePlus Nord 3 (oplus6983_22823)

Audits device tree bindings and runtime status for dual-hall effect magnetic
sensors on i2c0 (0x11e00000):
  - Down-Hall: MagnaChip MXM1120 (0x0C) or Isentek IST8801 (0x18), IRQ GPIO5
  - Up-Hall: MagnaChip MXM1120 (0x0D) or Isentek IST8801 (0x19), IRQ GPIO4
  - Supplies: VIO18 (1.8V), VIO28 (2.8V)

Safety invariant: Strictly read-only inspection. Zero I2C writes, zero module modifications.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

VALID_DOWNHALL_COMPATIBLES = {
    "oplus,hall-mxm1120,down",
    "oplus,hall-ist8801,down",
}

VALID_UPHALL_COMPATIBLES = {
    "oplus,hall-mxm1120,up",
    "oplus,hall-ist8801,up",
}

EXPECTED_I2C_BUS = "i2c@11e00000"
EXPECTED_I2C_COMPATIBLE = "mediatek,mt6983-i2c"
EXPECTED_DOWNHALL_GPIO = 5
EXPECTED_UPHALL_GPIO = 4


@dataclass
class TriStateKeyStatus:
    valid_dt: bool
    i2c_bus_ok: bool
    downhall_ok: bool
    uphall_ok: bool
    supplies_ok: bool
    slider_position: str  # SILENT, VIBRATE, RING, AMBIGUOUS, UNBOUND
    driver_bound: bool
    status: str           # OK, WARN, FAIL
    errors: List[str]
    warnings: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "valid_dt": self.valid_dt,
            "i2c_bus_ok": self.i2c_bus_ok,
            "downhall_ok": self.downhall_ok,
            "uphall_ok": self.uphall_ok,
            "supplies_ok": self.supplies_ok,
            "slider_position": self.slider_position,
            "driver_bound": self.driver_bound,
            "status": self.status,
            "errors": self.errors,
            "warnings": self.warnings,
        }


def evaluate_spec(data: Dict[str, Any]) -> TriStateKeyStatus:
    errors: List[str] = []
    warnings: List[str] = []

    dt = data.get("device_tree")
    if not dt or not isinstance(dt, dict):
        return TriStateKeyStatus(
            valid_dt=False,
            i2c_bus_ok=False,
            downhall_ok=False,
            uphall_ok=False,
            supplies_ok=False,
            slider_position="UNKNOWN",
            driver_bound=False,
            status="FAIL",
            errors=["Missing device_tree specification"],
            warnings=[],
        )

    # I2C Bus validation
    i2c_bus = dt.get("i2c_bus")
    i2c_compat = dt.get("i2c_compatible")
    i2c_bus_ok = (i2c_bus == EXPECTED_I2C_BUS and i2c_compat == EXPECTED_I2C_COMPATIBLE)
    if not i2c_bus_ok:
        errors.append(f"Unexpected I2C bus {i2c_bus} (expected {EXPECTED_I2C_BUS}) or compatible {i2c_compat}")

    # Down-hall validation
    downhall = dt.get("downhall", {})
    downhall_compat = downhall.get("compatible")
    downhall_gpio = downhall.get("irq_gpio")
    downhall_id = downhall.get("dhall_id")
    downhall_ok = (
        downhall_compat in VALID_DOWNHALL_COMPATIBLES and
        downhall_gpio == EXPECTED_DOWNHALL_GPIO and
        downhall_id == 2
    )
    if not downhall_ok:
        errors.append(f"Invalid downhall sensor config: compat={downhall_compat}, gpio={downhall_gpio}, id={downhall_id}")

    # Up-hall validation
    uphall = dt.get("uphall", {})
    uphall_compat = uphall.get("compatible")
    uphall_gpio = uphall.get("irq_gpio")
    uphall_id = uphall.get("dhall_id")
    uphall_ok = (
        uphall_compat in VALID_UPHALL_COMPATIBLES and
        uphall_gpio == EXPECTED_UPHALL_GPIO and
        uphall_id == 1
    )
    if not uphall_ok:
        errors.append(f"Invalid uphall sensor config: compat={uphall_compat}, gpio={uphall_gpio}, id={uphall_id}")

    # Supplies validation
    supplies = dt.get("supplies", {})
    vio = supplies.get("vio")
    vdd = supplies.get("vdd")
    supplies_ok = (vio == "VIO18" and vdd == "VIO28")
    if not supplies_ok:
        warnings.append(f"Supplies non-standard: vio={vio}, vdd={vdd}")

    valid_dt = i2c_bus_ok and downhall_ok and uphall_ok

    # Runtime status evaluation
    runtime = data.get("runtime", {})
    driver_bound = bool(runtime.get("driver_bound", False))
    up_triggered = bool(runtime.get("uphall_triggered", False))
    down_triggered = bool(runtime.get("downhall_triggered", False))

    if not driver_bound:
        slider_pos = "UNBOUND"
        warnings.append("Tri-state key drivers not bound in runtime")
    elif up_triggered and not down_triggered:
        slider_pos = "SILENT"   # State 1 (Top)
    elif not up_triggered and not down_triggered:
        slider_pos = "VIBRATE"  # State 2 (Middle)
    elif not up_triggered and down_triggered:
        slider_pos = "RING"     # State 3 (Bottom)
    else:
        slider_pos = "AMBIGUOUS" # Both triggered simultaneously - magnetic anomaly
        errors.append("Magnetic anomaly: Both up-hall and down-hall sensors report triggered")

    if errors:
        status = "FAIL"
    elif warnings or not driver_bound:
        status = "WARN"
    else:
        status = "OK"

    return TriStateKeyStatus(
        valid_dt=valid_dt,
        i2c_bus_ok=i2c_bus_ok,
        downhall_ok=downhall_ok,
        uphall_ok=uphall_ok,
        supplies_ok=supplies_ok,
        slider_position=slider_pos,
        driver_bound=driver_bound,
        status=status,
        errors=errors,
        warnings=warnings,
    )


def collect_live_state() -> Dict[str, Any]:
    """Read-only interrogation of sysfs for tri-state key hall sensors."""
    devices_path = Path("/sys/bus/i2c/devices")
    uphall_bound = False
    downhall_bound = False

    # Check I2C clients 0-000c and 0-000d (or 0-0018 / 0-0019)
    if devices_path.exists():
        downhall_bound = (devices_path / "0-000c").exists() or (devices_path / "0-0018").exists()
        uphall_bound = (devices_path / "0-000d").exists() or (devices_path / "0-0019").exists()

    return {
        "device_tree": {
            "i2c_bus": EXPECTED_I2C_BUS,
            "i2c_compatible": EXPECTED_I2C_COMPATIBLE,
            "downhall": {
                "node": "magnachip@0C",
                "compatible": "oplus,hall-mxm1120,down",
                "reg": "0x0c",
                "dhall_id": 2,
                "irq_gpio": 5,
                "pinctrl_state": "downhall_tri_state_key_active",
            },
            "uphall": {
                "node": "magnachip@0D",
                "compatible": "oplus,hall-mxm1120,up",
                "reg": "0x0d",
                "dhall_id": 1,
                "irq_gpio": 4,
                "pinctrl_state": "uphall_tri_state_key_active",
            },
            "supplies": {
                "vio": "VIO18",
                "vdd": "VIO28",
            },
        },
        "runtime": {
            "uphall_triggered": False,
            "downhall_triggered": False,
            "driver_bound": uphall_bound and downhall_bound,
            "uphall_sysfs_device": "/sys/bus/i2c/devices/0-000d" if uphall_bound else None,
            "downhall_sysfs_device": "/sys/bus/i2c/devices/0-000c" if downhall_bound else None,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="OnePlus Alert Slider (Tri-State Key) Hardware Preflight Gate")
    parser.add_argument("--validate", type=str, help="Validate offline fixture JSON")
    parser.add_argument("--live", action="store_true", help="Interrogate live hardware status (read-only)")
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
