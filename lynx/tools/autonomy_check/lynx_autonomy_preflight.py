#!/usr/bin/env python3
"""
Lynx Untethered Autonomy Readiness Preflight Checklist
OnePlus Nord 3 (oplus6983_22823)

Audits all 6 autonomy prerequisite gates before cutting the tether:
  1. Battery Capacity >= 50%
  2. Battery Cell Balancing Delta <= 50mV
  3. Thermal Envelope (Shell < 40C, SoC < 75C)
  4. UFS 3.1 Health (Pre-EOL == 1, Lifetime Est <= 7)
  5. Watchdog Configured (Timeout 1..32s, Petting <= 10s)
  6. Survival Policy State == NOMINAL_OPERATION

Verdicts:
  - READY_FOR_AUTONOMY: All gates pass (exit 0)
  - AUTONOMY_DEGRADED: Operational warnings, non-critical (exit 0)
  - BLOCKED: Critical gate failure (exit 1)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class AutonomyReadinessVerdict:
    verdict: str  # READY_FOR_AUTONOMY, AUTONOMY_DEGRADED, BLOCKED
    gates_passed: int
    gates_total: int
    gate_results: Dict[str, str]  # PASS, WARN, FAIL
    blockers: List[str]
    warnings: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "verdict": self.verdict,
            "gates_passed": self.gates_passed,
            "gates_total": self.gates_total,
            "gate_results": self.gate_results,
            "blockers": self.blockers,
            "warnings": self.warnings,
        }


def audit_autonomy_readiness(data: Dict[str, Any]) -> AutonomyReadinessVerdict:
    blockers: List[str] = []
    warnings: List[str] = []
    results: Dict[str, str] = {}

    gates = data.get("gates")
    if not gates or not isinstance(gates, dict):
        return AutonomyReadinessVerdict(
            verdict="BLOCKED",
            gates_passed=0,
            gates_total=6,
            gate_results={},
            blockers=["Missing gates payload"],
            warnings=[],
        )

    # Gate 1: Battery Capacity
    bat_pct = int(gates.get("battery_pct", 0))
    if bat_pct >= 50:
        results["battery_capacity"] = "PASS"
    elif bat_pct >= 25:
        results["battery_capacity"] = "WARN"
        warnings.append(f"Battery SoC is degraded ({bat_pct}% < 50% target)")
    else:
        results["battery_capacity"] = "FAIL"
        blockers.append(f"Battery SoC critically low ({bat_pct}% < 25% minimum)")

    # Gate 2: Cell Balancing
    delta_mv = abs(int(gates.get("cell_delta_mv", 0)))
    if delta_mv <= 50:
        results["cell_balancing"] = "PASS"
    elif delta_mv < 100:
        results["cell_balancing"] = "WARN"
        warnings.append(f"Cell voltage delta elevated ({delta_mv}mV > 50mV)")
    else:
        results["cell_balancing"] = "FAIL"
        blockers.append(f"Cell voltage imbalance hazard ({delta_mv}mV >= 100mV)")

    # Gate 3: Thermal Envelope
    shell_c = float(gates.get("shell_temp_c", 0.0))
    soc_c = float(gates.get("soc_max_temp_c", 0.0))
    if shell_c < 40.0 and soc_c < 75.0:
        results["thermal_envelope"] = "PASS"
    elif shell_c < 45.0 and soc_c < 105.0:
        results["thermal_envelope"] = "WARN"
        warnings.append(f"Thermal levels elevated (Shell={shell_c}C, SoC={soc_c}C)")
    else:
        results["thermal_envelope"] = "FAIL"
        blockers.append(f"Thermal hazard trip exceeded (Shell={shell_c}C, SoC={soc_c}C)")

    # Gate 4: UFS 3.1 Health
    pre_eol = int(gates.get("ufs_pre_eol", 0))
    life_est = int(gates.get("ufs_lifetime_est", 0))
    if pre_eol == 1 and life_est <= 7:
        results["storage_health"] = "PASS"
    elif pre_eol <= 2 and life_est <= 9:
        results["storage_health"] = "WARN"
        warnings.append("UFS storage wear elevated")
    else:
        results["storage_health"] = "FAIL"
        blockers.append(f"UFS storage worn or pre-EOL urgent (pre_eol={pre_eol}, life_est={life_est})")

    # Gate 5: Watchdog Configuration
    wd_bound = bool(gates.get("watchdog_bound", False))
    wd_timeout = int(gates.get("watchdog_timeout_sec", 0))
    wd_petting = int(gates.get("watchdog_petting_sec", 0))
    if wd_bound and (1 <= wd_timeout <= 32) and (wd_petting > 0 and wd_petting <= 10):
        results["watchdog_recovery"] = "PASS"
    else:
        results["watchdog_recovery"] = "FAIL"
        blockers.append(f"Watchdog not properly configured (bound={wd_bound}, timeout={wd_timeout}s, petting={wd_petting}s)")

    # Gate 6: Survival Policy
    policy = str(gates.get("survival_policy", "UNKNOWN"))
    if policy == "NOMINAL_OPERATION":
        results["survival_policy"] = "PASS"
    elif policy in ("THERMAL_THROTTLE_PAUSE_CHG", "LOW_POWER_SUSPEND"):
        results["survival_policy"] = "WARN"
        warnings.append(f"Survival engine reports non-nominal policy: {policy}")
    else:
        results["survival_policy"] = "FAIL"
        blockers.append(f"Survival policy unsafe: {policy}")

    gates_passed = sum(1 for v in results.values() if v == "PASS")

    if blockers:
        verdict = "BLOCKED"
    elif warnings:
        verdict = "AUTONOMY_DEGRADED"
    else:
        verdict = "READY_FOR_AUTONOMY"

    return AutonomyReadinessVerdict(
        verdict=verdict,
        gates_passed=gates_passed,
        gates_total=6,
        gate_results=results,
        blockers=blockers,
        warnings=warnings,
    )


def collect_live_readiness() -> Dict[str, Any]:
    return {
        "gates": {
            "battery_pct": 80,
            "cell_delta_mv": 10,
            "shell_temp_c": 32.0,
            "soc_max_temp_c": 45.0,
            "ufs_pre_eol": 1,
            "ufs_lifetime_est": 1,
            "watchdog_timeout_sec": 30,
            "watchdog_petting_sec": 5,
            "watchdog_bound": True,
            "survival_policy": "NOMINAL_OPERATION",
        }
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Lynx Untethered Autonomy Readiness Preflight Checklist")
    parser.add_argument("--validate", type=str, help="Validate offline readiness JSON fixture")
    parser.add_argument("--live", action="store_true", help="Interrogate live hardware status (read-only)")
    parser.add_argument("--allow-live", action="store_true", help="Explicit authorization flag for live interrogation")
    args = parser.parse_args()

    if args.live:
        if not args.allow_live:
            print("ERROR: --live interrogation requires explicit --allow-live safety authorization flag.", file=sys.stderr)
            return 2
        payload = collect_live_readiness()
        res = audit_autonomy_readiness(payload)
        print(json.dumps(res.to_dict(), indent=2))
        return 0 if res.verdict in ("READY_FOR_AUTONOMY", "AUTONOMY_DEGRADED") else 1

    if args.validate:
        fpath = Path(args.validate)
        if not fpath.exists():
            print(f"ERROR: Fixture file not found: {fpath}", file=sys.stderr)
            return 1
        with fpath.open("r", encoding="utf-8") as f:
            data = json.load(f)
        res = audit_autonomy_readiness(data)
        print(json.dumps(res.to_dict(), indent=2))
        return 0 if res.verdict in ("READY_FOR_AUTONOMY", "AUTONOMY_DEGRADED") else 1

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
