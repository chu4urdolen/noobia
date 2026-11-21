#!/usr/bin/env python3
"""lynx-survivald — Lynx (OnePlus Nord 3 / MT6983) autonomous survival & power daemon.

Round 8 item D26 (queue: LYNX-ROUND-8-QUEUE-BANSHEE-20261121.md).
Executes the 4-state survival decision engine established in B28
(lynx/tools/survival/lynx_survival_engine.py) as a background polling daemon.

Telemetry sources (read-only; verified facts from B18/B22/B23 docs):
  * Fuel gauge   : TI BQ28Z610, i2c7 @ 0x55 (`/sys/bus/i2c/devices/7-0055/battery_snapshot`)
  * SuperVOOC chg: MT6375 sub-PMIC, i2c5 @ 0x34 (2S pack, 7.4 V nom / 8.7 V chg)
  * Thermals     : LVTS array + NTC zones (soc_max 116.5 C crit; skin 40/45 C bands)

Safety contract (enforced in test_lynx_survivald.py):
  * Default mode is OFFLINE SIMULATION: `--validate FIXTURE` runs the full
    polling loop — telemetry evaluation, action dispatch, state-broker
    publication — in-process from hermetic JSON. Zero hardware contact.
  * Live mode requires BOTH `--live` and `--allow-live`; it polls read-only
    sysfs sources and still dispatches only SIMULATED actions (actuation
    stays gated behind the autonomy readiness checklist, B31).
  * Actions are data (SimulatedAction records), never executed: CPU governor
    switching, charging current limit (<= 500 mA), SCP/LPM suspend trigger,
    graceful shutdown sequence — all reported, none performed.
  * SIGTERM/SIGINT: final broker publication with STOPPED_BY_SIGNAL, clean exit.
"""

from __future__ import annotations

import argparse
import json
import signal
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

# --- B28 engine thresholds (mirrored; keep in sync with lynx_survival_engine.py)
CRITICAL_BATTERY_SHUTDOWN_PCT = 5
LOW_BATTERY_SUSPEND_PCT = 15
WARN_BATTERY_PCT = 25
EMERGENCY_SKIN_TEMP_C = 45.0
THROTTLE_SKIN_TEMP_C = 40.0
EMERGENCY_SOC_TEMP_C = 105.0
THROTTLE_SOC_TEMP_C = 75.0
POLICY_CHARGE_LIMIT_MA = 500

POLL_INTERVAL_DEFAULT_S = 10.0
POLL_INTERVAL_MIN_S = 1.0
POLL_INTERVAL_MAX_S = 60.0
DEFAULT_STATE_FILE = "/tmp/lynx_survival_state.json"

# B28 policy states (full names) + queue D26 short names.
NOMINAL_OPERATION = "NOMINAL_OPERATION"
THERMAL_THROTTLE_PAUSE_CHG = "THERMAL_THROTTLE_PAUSE_CHG"
LOW_POWER_SUSPEND = "LOW_POWER_SUSPEND"
EMERGENCY_SHUTDOWN = "EMERGENCY_SHUTDOWN"
POLICY_STATES = (
    NOMINAL_OPERATION,
    THERMAL_THROTTLE_PAUSE_CHG,
    LOW_POWER_SUSPEND,
    EMERGENCY_SHUTDOWN,
)
SHORT_NAMES = {
    NOMINAL_OPERATION: "NOMINAL",
    THERMAL_THROTTLE_PAUSE_CHG: "THERMAL_THROTTLE",
    LOW_POWER_SUSPEND: "LOW_POWER_SUSPEND",
    EMERGENCY_SHUTDOWN: "EMERGENCY_SHUTDOWN",
}
FINAL_STOPPED = "STOPPED_BY_SIGNAL"


@dataclass
class SpecError:
    reasons: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.reasons

    def add(self, reason: str) -> None:
        self.reasons.append(reason)


@dataclass
class SimulatedAction:
    action: str
    target: str
    params: Dict[str, Any]
    simulated: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action": self.action,
            "target": self.target,
            "params": self.params,
            "simulated": self.simulated,
        }


@dataclass
class PolicyDecision:
    policy_state: str
    status: str
    reasons: List[str]
    actions: List[SimulatedAction]

    @property
    def short_state(self) -> str:
        return SHORT_NAMES[self.policy_state]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "state": self.short_state,
            "policy_state": self.policy_state,
            "status": self.status,
            "reasons": self.reasons,
            "actions": [a.to_dict() for a in self.actions],
        }


def validate_survivald_spec(doc: Any) -> SpecError:
    err = SpecError()
    if not isinstance(doc, dict):
        return SpecError(["fixture is not a JSON object"])
    eng = doc.get("engine")
    if not isinstance(eng, dict):
        return SpecError(["missing 'engine' section"])
    interval = eng.get("poll_interval_s")
    if (
        not isinstance(interval, (int, float))
        or isinstance(interval, bool)
        or not (POLL_INTERVAL_MIN_S <= interval <= POLL_INTERVAL_MAX_S)
    ):
        err.add(
            f"engine.poll_interval_s must be in [{POLL_INTERVAL_MIN_S}, {POLL_INTERVAL_MAX_S}]"
        )
    polls = eng.get("max_polls")
    if not isinstance(polls, int) or isinstance(polls, bool) or polls < 0:
        err.add("engine.max_polls must be a non-negative int (0 = unbounded, live only)")
    series = doc.get("telemetry_series")
    if not isinstance(series, list) or not series:
        err.add("telemetry_series must be a non-empty list")
    sig = doc.get("signal")
    if sig is not None and (
        not isinstance(sig, dict) or sig.get("kind") not in ("SIGTERM", "SIGINT")
    ):
        err.add("signal must be null or {kind: SIGTERM|SIGINT, at_poll: N}")
    if polls == 0 and sig is None:
        err.add("offline simulation requires bounded max_polls or a signal stop")
    return err


def evaluate_telemetry(telem: Any) -> PolicyDecision:
    """B28 4-state decision logic. Pure; no hardware, no actuation."""
    if not isinstance(telem, dict):
        return PolicyDecision(
            EMERGENCY_SHUTDOWN,
            "CRITICAL",
            ["telemetry sample is not a JSON object"],
            [SimulatedAction("graceful_shutdown", "lynx-agent", {"sequence": ["stop-agents", "flush-broker", "sync", "poweroff"]})],
        )
    battery = telem.get("battery_pct")
    shell = telem.get("shell_temp_c")
    soc = telem.get("soc_max_temp_c")
    reasons: List[str] = []
    if not isinstance(battery, (int, float)) or isinstance(battery, bool):
        reasons.append(f"battery_pct {battery!r} is not numeric")
    if not isinstance(shell, (int, float)) or isinstance(shell, bool):
        reasons.append(f"shell_temp_c {shell!r} is not numeric")
    if not isinstance(soc, (int, float)) or isinstance(soc, bool):
        reasons.append(f"soc_max_temp_c {soc!r} is not numeric")
    if reasons:
        return PolicyDecision(
            EMERGENCY_SHUTDOWN,
            "CRITICAL",
            reasons,
            [SimulatedAction("graceful_shutdown", "lynx-agent", {"sequence": ["stop-agents", "flush-broker", "sync", "poweroff"]})],
        )
    battery, shell, soc = float(battery), float(shell), float(soc)

    actions: List[SimulatedAction] = []
    if battery <= CRITICAL_BATTERY_SHUTDOWN_PCT:
        reasons.append(f"battery {battery:.1f}% <= emergency reserve {CRITICAL_BATTERY_SHUTDOWN_PCT}%")
    if shell >= EMERGENCY_SKIN_TEMP_C:
        reasons.append(f"skin temp {shell:.1f}C >= emergency cutoff {EMERGENCY_SKIN_TEMP_C}C")
    if soc >= EMERGENCY_SOC_TEMP_C:
        reasons.append(f"SoC die temp {soc:.1f}C >= emergency trip {EMERGENCY_SOC_TEMP_C}C")
    if reasons:
        return PolicyDecision(
            EMERGENCY_SHUTDOWN,
            "CRITICAL",
            reasons,
            [
                SimulatedAction("stop_agents", "lynx-agent", {"duty_cycle": "STOPPED"}),
                SimulatedAction("flush_broker", DEFAULT_STATE_FILE, {"final": True}),
                SimulatedAction("sync", "/rootfs", {"simulated": True}),
                SimulatedAction("poweroff", "mt6983-pwrkey", {"simulated": True}),
            ],
        )

    throttle = False
    if shell >= THROTTLE_SKIN_TEMP_C:
        throttle = True
        reasons.append(f"skin temp {shell:.1f}C in throttle band (>= {THROTTLE_SKIN_TEMP_C}C)")
    if soc >= THROTTLE_SOC_TEMP_C:
        throttle = True
        reasons.append(f"SoC die temp {soc:.1f}C in throttle band (>= {THROTTLE_SOC_TEMP_C}C)")
    if battery <= LOW_BATTERY_SUSPEND_PCT:
        reasons.append(f"battery {battery:.1f}% in reserve band (<= {LOW_BATTERY_SUSPEND_PCT}%)")
        return PolicyDecision(
            LOW_POWER_SUSPEND,
            "WARN" if battery > CRITICAL_BATTERY_SHUTDOWN_PCT else "CRITICAL",
            reasons,
            [
                SimulatedAction("set_cpu_governor", "cpu0-cpufreq", {"governor": "powersave"}),
                SimulatedAction("limit_charge_current", "mt6375-chg", {"limit_ma": POLICY_CHARGE_LIMIT_MA}),
                SimulatedAction("trigger_suspend", "scp-lpm", {"mode": "C_SLEEP", "simulated": True}),
                SimulatedAction("stop_agents", "lynx-agent", {"duty_cycle": "STOPPED"}),
            ],
        )
    if throttle:
        return PolicyDecision(
            THERMAL_THROTTLE_PAUSE_CHG,
            "WARN",
            reasons,
            [
                SimulatedAction("set_cpu_governor", "cpu0-cpufreq", {"governor": "powersave"}),
                SimulatedAction("limit_charge_current", "mt6375-chg", {"limit_ma": POLICY_CHARGE_LIMIT_MA}),
                SimulatedAction("throttle_agents", "lynx-agent", {"duty_cycle": "REDUCED"}),
            ],
        )

    if battery <= WARN_BATTERY_PCT:
        reasons.append(f"battery {battery:.1f}% at/below warn band ({WARN_BATTERY_PCT}%) — watch")
    actions.append(SimulatedAction("set_cpu_governor", "cpu0-cpufreq", {"governor": "schedutil"}))
    actions.append(SimulatedAction("charge_policy", "mt6375-chg", {"policy": "NORMAL_80W_SUPERVOOC"}))
    actions.append(SimulatedAction("agent_duty", "lynx-agent", {"duty_cycle": "FULL"}))
    return PolicyDecision(NOMINAL_OPERATION, "OK", reasons, actions)


def publish_state(path: Path, report: Dict[str, Any]) -> None:
    """Status broker: publish current policy state (readers poll this file)."""
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


def simulate_poll_loop(doc: Dict[str, Any], state_file: Path) -> Dict[str, Any]:
    """Deterministic offline polling loop: evaluate -> dispatch -> publish."""
    series: List[Any] = list(doc["telemetry_series"])
    max_polls = int(doc["engine"]["max_polls"])
    signal_spec = doc.get("signal")
    signal_poll = int(signal_spec.get("at_poll", 1)) if isinstance(signal_spec, dict) else None
    if max_polls == 0 and signal_poll is None:
        raise ValueError("offline simulation requires bounded max_polls or a signal stop")
    unbounded = max_polls == 0
    limit = max_polls if not unbounded else (signal_poll or 1)

    transcript: List[Dict[str, Any]] = []
    polls = 0
    final_state = "NOMINAL"
    final_decision: Optional[PolicyDecision] = None
    terminated_early = False

    poll = 1
    while unbounded or poll <= limit:
        if signal_poll == poll:
            report = {
                "mode": "offline-simulation",
                "state": FINAL_STOPPED,
                "polls_executed": polls,
                "timestamp": "simulated",
            }
            publish_state(state_file, report)
            transcript.append({"poll": poll, "event": "signal", "action": "final broker publish STOPPED_BY_SIGNAL, clean exit"})
            final_state = FINAL_STOPPED
            break
        telem = series[min(poll - 1, len(series) - 1)]
        decision = evaluate_telemetry(telem)
        polls += 1
        final_decision = decision
        final_state = decision.short_state
        report = {
            "mode": "offline-simulation",
            "state": decision.short_state,
            "policy_state": decision.policy_state,
            "status": decision.status,
            "battery_pct": telem.get("battery_pct") if isinstance(telem, dict) else None,
            "shell_temp_c": telem.get("shell_temp_c") if isinstance(telem, dict) else None,
            "soc_max_temp_c": telem.get("soc_max_temp_c") if isinstance(telem, dict) else None,
            "reasons": decision.reasons,
            "actions": [a.to_dict() for a in decision.actions],
            "poll": poll,
            "timestamp": "simulated",
        }
        publish_state(state_file, report)
        transcript.append({"poll": poll, "event": "evaluate", **decision.to_dict()})
        if decision.policy_state == EMERGENCY_SHUTDOWN:
            terminated_early = True
            transcript.append({"poll": poll, "event": "terminal", "action": "EMERGENCY_SHUTDOWN sequence dispatched (simulated); loop ends"})
            break
        if not unbounded and poll >= limit:
            break
        poll += 1

    return {
        "final_state": final_state,
        "final_policy_state": final_decision.policy_state if final_decision else None,
        "polls_executed": polls,
        "terminated_early": terminated_early,
        "transcript": transcript,
    }


def collect_live_telemetry() -> Dict[str, Any]:
    """Read-only live telemetry (B23 gauge path, thermal sysfs, charger sysfs)."""
    telem: Dict[str, Any] = {}
    gauge = Path("/sys/bus/i2c/devices/7-0055/battery_snapshot")
    if gauge.exists():
        text = gauge.read_text(encoding="utf-8", errors="replace")
        for line in text.splitlines():
            if line.lower().startswith("soc:") or line.lower().startswith("capacity:"):
                try:
                    telem["battery_pct"] = int(line.split(":")[1].strip().rstrip("%"))
                except (IndexError, ValueError):
                    pass
                break
    if "battery_pct" not in telem:
        supply = Path("/sys/class/power_supply/battery/capacity")
        if supply.exists():
            try:
                telem["battery_pct"] = int(supply.read_text(encoding="utf-8").strip())
            except (OSError, ValueError):
                pass
    skin: Optional[float] = None
    die: Optional[float] = None
    for zone in sorted(Path("/sys/class/thermal").glob("thermal_zone*")):
        try:
            temp = int((zone / "temp").read_text(encoding="utf-8")) / 1000.0
        except (OSError, ValueError):
            continue
        try:
            typ = (zone / "type").read_text(encoding="utf-8").strip().lower()
        except OSError:
            continue
        if "skin" in typ or "quiet" in typ or "chassis" in typ:
            skin = temp
        elif "soc" in typ or "cpu" in typ:
            die = temp if die is None else min(die, temp)
    telem.setdefault("shell_temp_c", skin if skin is not None else 0.0)
    telem.setdefault("soc_max_temp_c", die if die is not None else 0.0)
    return telem


_STOP_REQUESTED = False


def _install_stop_handlers() -> None:
    def _on_signal(signum: int, _frame: Any) -> None:
        global _STOP_REQUESTED
        _STOP_REQUESTED = True

    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)


def run_live(interval_s: float, max_polls: int, state_file: Path, wall_cap_s: float) -> int:
    """Live polling: read-only telemetry + SIMULATED action dispatch + broker publish."""
    if not (POLL_INTERVAL_MIN_S <= interval_s <= POLL_INTERVAL_MAX_S):
        print(f"FAIL: poll interval {interval_s}s outside [{POLL_INTERVAL_MIN_S}, {POLL_INTERVAL_MAX_S}]", file=sys.stderr)
        return 1
    _install_stop_handlers()
    transcript: List[Dict[str, Any]] = []
    polls = 0
    final_state = NOMINAL_OPERATION
    start = time.monotonic()
    poll = 1
    while max_polls == 0 or poll <= max_polls:
        if _STOP_REQUESTED:
            publish_state(state_file, {"mode": "live", "state": FINAL_STOPPED, "polls_executed": polls, "timestamp": time.time()})
            final_state = FINAL_STOPPED
            break
        if wall_cap_s > 0 and (time.monotonic() - start) >= wall_cap_s:
            final_state = "LIVE_WALL_TIMEOUT"
            break
        telem = collect_live_telemetry()
        decision = evaluate_telemetry(telem)
        polls += 1
        final_state = decision.policy_state
        report = {
            "mode": "live",
            "state": decision.short_state,
            "policy_state": decision.policy_state,
            "status": decision.status,
            "telemetry": telem,
            "reasons": decision.reasons,
            "actions": [a.to_dict() for a in decision.actions],
            "poll": poll,
            "timestamp": time.time(),
        }
        publish_state(state_file, report)
        transcript.append({"poll": poll, "event": "evaluate", **decision.to_dict()})
        if decision.policy_state == EMERGENCY_SHUTDOWN:
            break
        if max_polls and poll >= max_polls:
            break
        poll += 1
        time.sleep(interval_s)
    report = {
        "mode": "live",
        "final_policy_state": final_state,
        "polls_executed": polls,
        "transcript": transcript,
    }
    print(json.dumps(report, indent=2))
    return 0


def run_offline(fixture_path: Path, state_file: Path) -> int:
    try:
        doc = json.loads(fixture_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"FAIL: fixture is not valid JSON: {exc}", file=sys.stderr)
        return 1
    err = validate_survivald_spec(doc)
    if not err.ok:
        print(f"FAIL: MALFORMED_SPEC: {err.reasons}", file=sys.stderr)
        return 1
    try:
        result = simulate_poll_loop(doc, state_file)
    except ValueError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    expected = doc.get("expected_final_state")
    known = (*SHORT_NAMES.values(), *POLICY_STATES, FINAL_STOPPED)
    if expected not in known:
        print(f"FAIL: expected_final_state {expected!r} is not a known state", file=sys.stderr)
        return 1
    result["expected_final_state"] = expected
    if result["final_state"] != expected:
        result["verdict"] = "MISMATCH"
        print(
            f"FAIL: final_state {result['final_state']!r} != expected {expected!r}",
            file=sys.stderr,
        )
        print(json.dumps(result, indent=2))
        return 1
    result["verdict"] = "PASS"
    print(json.dumps(result, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lynx-survivald",
        description="Lynx autonomous survival & power management daemon (D26, executes the B28 engine).",
    )
    parser.add_argument("--validate", type=str, metavar="FIXTURE", help="Run offline simulation against FIXTURE JSON")
    parser.add_argument("--live", action="store_true", help="Run live polling (requires --allow-live)")
    parser.add_argument("--allow-live", action="store_true", help="Explicit authorization for live polling")
    parser.add_argument("--polls", type=int, default=0, help="Max polls; 0 = unbounded daemon mode (live only)")
    parser.add_argument("--interval", type=float, default=POLL_INTERVAL_DEFAULT_S, help="Seconds between polls")
    parser.add_argument("--wall-cap", type=float, default=0.0, help="Live-only wall-clock cap in seconds; 0 = none")
    parser.add_argument("--state-file", type=str, default=DEFAULT_STATE_FILE, help="Status broker state file")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.validate and not args.live:
        parser.print_help()
        return 2
    if args.live and not args.allow_live:
        print("REFUSED: live polling requires BOTH --live and --allow-live", file=sys.stderr)
        return 2
    state_file = Path(args.state_file) if args.state_file else Path(DEFAULT_STATE_FILE)
    if args.validate:
        return run_offline(Path(args.validate), state_file)
    return run_live(args.interval, args.polls, state_file, args.wall_cap)


if __name__ == "__main__":
    sys.exit(main())
