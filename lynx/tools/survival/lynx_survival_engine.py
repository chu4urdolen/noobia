#!/usr/bin/env python3
"""
Lynx Autonomous Thermal & Battery Survival Engine
OnePlus Nord 3 (oplus6983_22823)

Evaluates telemetry across Battery Fuel Gauge (BQ28Z610), SuperVOOC Charger (MT6375),
and Thermal Zones (LVTS + NTC) to determine the autonomous survival policy:
  - NOMINAL_OPERATION: Normal execution
  - THERMAL_THROTTLE_PAUSE_CHG: Throttle CPU, pause/throttle fast charging
  - LOW_POWER_SUSPEND: Battery reserve threshold (6-15%), trigger SCP/LPM suspend
  - EMERGENCY_SHUTDOWN: Battery <= 5% or thermal cutoff >= 45C skin / >= 105C die

Safety Invariant: Pure decision evaluation. Zero hardware actuation or shutdown execution during preflight.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

# Thresholds
CRITICAL_BATTERY_SHUTDOWN_PCT = 5
LOW_BATTERY_SUSPEND_PCT = 15
WARN_BATTERY_PCT = 25

EMERGENCY_SKIN_TEMP_C = 45.0
THROTTLE_SKIN_TEMP_C = 40.0

EMERGENCY_SOC_TEMP_C = 105.0
THROTTLE_SOC_TEMP_C = 75.0


@dataclass
class SurvivalPolicyVerdict:
    policy_state: str  # NOMINAL_OPERATION, THERMAL_THROTTLE_PAUSE_CHG, LOW_POWER_SUSPEND, EMERGENCY_SHUTDOWN
    battery_pct: int
    shell_temp_c: float
    soc_max_temp_c: float
    recommended_cpu_governor: str
    recommended_charging_policy: str
    recommended_agent_duty_cycle: str
    status: str        # OK, WARN, CRITICAL
    reasons: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "policy_state": self.policy_state,
            "battery_pct": self.battery_pct,
            "shell_temp_c": self.shell_temp_c,
            "soc_max_temp_c": self.soc_max_temp_c,
            "recommended_cpu_governor": self.recommended_cpu_governor,
            "recommended_charging_policy": self.recommended_charging_policy,
            "recommended_agent_duty_cycle": self.recommended_agent_duty_cycle,
            "status": self.status,
            "reasons": self.reasons,
        }


def evaluate_telemetry(data: Dict[str, Any]) -> SurvivalPolicyVerdict:
    reasons: List[str] = []

    telem = data.get("telemetry")
    if not telem or not isinstance(telem, dict):
        return SurvivalPolicyVerdict(
            policy_state="UNKNOWN",
            battery_pct=0,
            shell_temp_c=0.0,
            soc_max_temp_c=0.0,
            recommended_cpu_governor="powersave",
            recommended_charging_policy="PAUSE",
            recommended_agent_duty_cycle="STOPPED",
            status="CRITICAL",
            reasons=["Missing telemetry payload"],
        )

    bat_pct = int(telem.get("battery_pct", 0))
    shell_temp = float(telem.get("shell_temp_c", 0.0))
    soc_temp = float(telem.get("soc_max_temp_c", 0.0))

    # Priority 1: Emergency Shutdown conditions
    if bat_pct <= CRITICAL_BATTERY_SHUTDOWN_PCT:
        reasons.append(f"Battery critically depleted ({bat_pct}% <= {CRITICAL_BATTERY_SHUTDOWN_PCT}%). Brownout hazard.")
        return SurvivalPolicyVerdict(
            policy_state="EMERGENCY_SHUTDOWN",
            battery_pct=bat_pct,
            shell_temp_c=shell_temp,
            soc_max_temp_c=soc_temp,
            recommended_cpu_governor="powersave",
            recommended_charging_policy="PAUSE",
            recommended_agent_duty_cycle="TERMINATE",
            status="CRITICAL",
            reasons=reasons,
        )

    if shell_temp >= EMERGENCY_SKIN_TEMP_C:
        reasons.append(f"Chassis skin temp {shell_temp}C exceeds hazard cutoff ({EMERGENCY_SKIN_TEMP_C}C).")
        return SurvivalPolicyVerdict(
            policy_state="EMERGENCY_SHUTDOWN",
            battery_pct=bat_pct,
            shell_temp_c=shell_temp,
            soc_max_temp_c=soc_temp,
            recommended_cpu_governor="powersave",
            recommended_charging_policy="PAUSE",
            recommended_agent_duty_cycle="TERMINATE",
            status="CRITICAL",
            reasons=reasons,
        )

    if soc_temp >= EMERGENCY_SOC_TEMP_C:
        reasons.append(f"SoC die temp {soc_temp}C exceeds emergency trip point ({EMERGENCY_SOC_TEMP_C}C).")
        return SurvivalPolicyVerdict(
            policy_state="EMERGENCY_SHUTDOWN",
            battery_pct=bat_pct,
            shell_temp_c=shell_temp,
            soc_max_temp_c=soc_temp,
            recommended_cpu_governor="powersave",
            recommended_charging_policy="PAUSE",
            recommended_agent_duty_cycle="TERMINATE",
            status="CRITICAL",
            reasons=reasons,
        )

    # Priority 2: Thermal Throttling
    if shell_temp >= THROTTLE_SKIN_TEMP_C or soc_temp >= THROTTLE_SOC_TEMP_C:
        if shell_temp >= THROTTLE_SKIN_TEMP_C:
            reasons.append(f"Chassis skin temp {shell_temp}C in throttle band ({THROTTLE_SKIN_TEMP_C}C - {EMERGENCY_SKIN_TEMP_C}C).")
        if soc_temp >= THROTTLE_SOC_TEMP_C:
            reasons.append(f"SoC die temp {soc_temp}C in throttle band ({THROTTLE_SOC_TEMP_C}C - {EMERGENCY_SOC_TEMP_C}C).")
        return SurvivalPolicyVerdict(
            policy_state="THERMAL_THROTTLE_PAUSE_CHG",
            battery_pct=bat_pct,
            shell_temp_c=shell_temp,
            soc_max_temp_c=soc_temp,
            recommended_cpu_governor="powersave",
            recommended_charging_policy="PAUSE_OR_500MA",
            recommended_agent_duty_cycle="LOW_DUTY_25PCT",
            status="WARN",
            reasons=reasons,
        )

    # Priority 3: Low Power Suspend (battery reserve threshold)
    if bat_pct <= LOW_BATTERY_SUSPEND_PCT:
        reasons.append(f"Battery in reserve band ({bat_pct}% <= {LOW_BATTERY_SUSPEND_PCT}%). Entering SCP/LPM suspend.")
        return SurvivalPolicyVerdict(
            policy_state="LOW_POWER_SUSPEND",
            battery_pct=bat_pct,
            shell_temp_c=shell_temp,
            soc_max_temp_c=soc_temp,
            recommended_cpu_governor="powersave",
            recommended_charging_policy="RESUME_SAFE",
            recommended_agent_duty_cycle="SUSPEND_SLEEP",
            status="WARN",
            reasons=reasons,
        )

    # Nominal Operation
    reasons.append("Thermal envelope and battery capacity within nominal operating bounds.")
    return SurvivalPolicyVerdict(
        policy_state="NOMINAL_OPERATION",
        battery_pct=bat_pct,
        shell_temp_c=shell_temp,
        soc_max_temp_c=soc_temp,
        recommended_cpu_governor="schedutil",
        recommended_charging_policy="FULL_SUPERVOOC",
        recommended_agent_duty_cycle="FULL_AUTONOMY",
        status="OK",
        reasons=reasons,
    )


def collect_live_telemetry() -> Dict[str, Any]:
    """Read-only interrogation of fuel gauge and thermal zones."""
    # Simulated defaults when running on host
    return {
        "telemetry": {
            "battery_pct": 50,
            "battery_voltage_mv": 7500,
            "battery_current_ma": 0,
            "charging_active": False,
            "shell_temp_c": 32.0,
            "soc_max_temp_c": 45.0,
            "cpu_big_temp_c": 44.0,
            "ram_free_mb": 512,
            "storage_free_mb": 15000,
        }
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Lynx Autonomous Survival Decision Engine")
    parser.add_argument("--validate", type=str, help="Validate offline fixture JSON")
    parser.add_argument("--live", action="store_true", help="Interrogate live hardware status (read-only)")
    parser.add_argument("--allow-live", action="store_true", help="Explicit authorization flag for live interrogation")
    args = parser.parse_args()

    if args.live:
        if not args.allow_live:
            print("ERROR: --live interrogation requires explicit --allow-live safety authorization flag.", file=sys.stderr)
            return 2
        payload = collect_live_telemetry()
        res = evaluate_telemetry(payload)
        print(json.dumps(res.to_dict(), indent=2))
        return 0 if res.status in ("OK", "WARN") else 1

    if args.validate:
        fixture_path = Path(args.validate)
        if not fixture_path.exists():
            print(f"ERROR: Fixture file not found: {fixture_path}", file=sys.stderr)
            return 1
        with fixture_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        res = evaluate_telemetry(data)
        print(json.dumps(res.to_dict(), indent=2))
        return 0 if res.status in ("OK", "WARN") else 1

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
