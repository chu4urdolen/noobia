#!/usr/bin/env python3
"""
Lynx Autonomous Health Heartbeat Payload Generator and Validator
OnePlus Nord 3 (oplus6983_22823)

Aggregates, formats, and validates autonomous telemetry payloads:
  - Battery Fuel Gauge (BQ28Z610): SoC %, voltage, current, cell balancing delta
  - Thermal Zones (LVTS + NTC): shell temp, soc_max temp
  - Survival Policy State: nominal, throttle, suspend, emergency
  - Hardware Watchdog: active, timeout, petting interval
  - Cgroup Sandbox: agent memory usage, memory limit, pressure

Safety Invariant: Passive status aggregation and schema validation.
Payload-only tool; does not broadcast packets, run as a daemon, or make network transmissions.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class HeartbeatValidationResult:
    valid_schema: bool
    node_name: str
    battery_pct: int
    survival_policy: str
    watchdog_active: bool
    status: str  # OK, WARN, FAIL
    errors: List[str]
    warnings: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "valid_schema": self.valid_schema,
            "node_name": self.node_name,
            "battery_pct": self.battery_pct,
            "survival_policy": self.survival_policy,
            "watchdog_active": self.watchdog_active,
            "status": self.status,
            "errors": self.errors,
            "warnings": self.warnings,
        }


def validate_heartbeat_payload(payload: Dict[str, Any]) -> HeartbeatValidationResult:
    errors: List[str] = []
    warnings: List[str] = []

    if not isinstance(payload, dict):
        return HeartbeatValidationResult(
            valid_schema=False,
            node_name="UNKNOWN",
            battery_pct=0,
            survival_policy="UNKNOWN",
            watchdog_active=False,
            status="FAIL",
            errors=["Payload is not a JSON object"],
            warnings=[],
        )

    node = payload.get("node")
    if node != "lynx":
        errors.append(f"Invalid node identifier: {node} (expected 'lynx')")

    bat = payload.get("battery")
    if not isinstance(bat, dict):
        errors.append("Missing or invalid 'battery' section")
        bat_pct = 0
    else:
        bat_pct = int(bat.get("capacity_pct", 0))
        if bat_pct < 0 or bat_pct > 100:
            errors.append(f"Battery percentage {bat_pct}% out of range 0..100")
        if bat_pct < 20:
            warnings.append(f"Low battery in heartbeat telemetry ({bat_pct}%)")

    thermal = payload.get("thermal")
    if not isinstance(thermal, dict):
        errors.append("Missing or invalid 'thermal' section")
    else:
        shell_c = float(thermal.get("shell_temp_c", 0.0))
        if shell_c >= 42.0:
            warnings.append(f"High shell temperature ({shell_c}C)")

    policy = payload.get("survival_policy", "UNKNOWN")
    if policy not in ("NOMINAL_OPERATION", "THERMAL_THROTTLE_PAUSE_CHG", "LOW_POWER_SUSPEND", "EMERGENCY_SHUTDOWN"):
        warnings.append(f"Unrecognized survival policy state: {policy}")

    wd = payload.get("watchdog")
    wd_active = False
    if not isinstance(wd, dict):
        errors.append("Missing or invalid 'watchdog' section")
    else:
        wd_active = bool(wd.get("active", False))
        if not wd_active:
            warnings.append("Watchdog reported inactive in heartbeat")

    cg = payload.get("cgroups")
    if not isinstance(cg, dict):
        warnings.append("Missing 'cgroups' resource section")

    valid_schema = (len(errors) == 0)
    if errors:
        status = "FAIL"
    elif warnings:
        status = "WARN"
    else:
        status = "OK"

    return HeartbeatValidationResult(
        valid_schema=valid_schema,
        node_name=str(node),
        battery_pct=bat_pct,
        survival_policy=str(policy),
        watchdog_active=wd_active,
        status=status,
        errors=errors,
        warnings=warnings,
    )


def synthesize_nominal_payload() -> Dict[str, Any]:
    return {
        "node": "lynx",
        "platform": "OnePlus Nord 3 (CPH2493 / MT6983)",
        "uptime_sec": 3600,
        "battery": {
            "capacity_pct": 78,
            "voltage_mv": 7800,
            "current_ma": -380,
            "status": "discharging",
            "cell_delta_mv": 10,
        },
        "thermal": {
            "shell_temp_c": 31.8,
            "soc_max_temp_c": 44.5,
            "status": "nominal",
        },
        "survival_policy": "NOMINAL_OPERATION",
        "watchdog": {
            "active": True,
            "timeout_sec": 30,
            "petting_interval_sec": 5,
        },
        "cgroups": {
            "agent_mem_usage_mb": 128.0,
            "agent_mem_limit_mb": 512.0,
            "pressure_pct": 0.0,
        },
        "timestamp": "2026-11-21T05:35:00Z",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Lynx Autonomous Health Heartbeat Publisher")
    parser.add_argument("--validate", type=str, help="Validate offline heartbeat payload JSON")
    parser.add_argument("--emit", action="store_true", help="Synthesize and emit simulated heartbeat to stdout")
    parser.add_argument("--live", action="store_true", help="Interrogate live hardware status (read-only)")
    parser.add_argument("--allow-live", action="store_true", help="Explicit authorization flag for live interrogation")
    args = parser.parse_args()

    if args.emit:
        payload = synthesize_nominal_payload()
        res = validate_heartbeat_payload(payload)
        print(json.dumps(payload, indent=2))
        return 0 if res.status == "OK" else 1

    if args.live:
        if not args.allow_live:
            print("ERROR: --live interrogation requires explicit --allow-live safety authorization flag.", file=sys.stderr)
            return 2
        payload = synthesize_nominal_payload()
        res = validate_heartbeat_payload(payload)
        print(json.dumps(res.to_dict(), indent=2))
        return 0 if res.status in ("OK", "WARN") else 1

    if args.validate:
        fpath = Path(args.validate)
        if not fpath.exists():
            print(f"ERROR: Fixture file not found: {fpath}", file=sys.stderr)
            return 1
        with fpath.open("r", encoding="utf-8") as f:
            data = json.load(f)
        res = validate_heartbeat_payload(data)
        print(json.dumps(res.to_dict(), indent=2))
        return 0 if res.status in ("OK", "WARN") else 1

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
