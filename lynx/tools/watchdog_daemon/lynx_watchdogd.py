#!/usr/bin/env python3
"""lynx-watchdogd — Lynx (OnePlus Nord 3 / MT6983) TOPRGU watchdog supervision daemon.

Round 8 item D25 (queue: LYNX-ROUND-8-QUEUE-BANSHEE-20261121.md).

Hardware (verified facts, see LYNX-WATCHDOG-RECOVERY-PREFLIGHT-20261121.md, B27):
  * DT node   : watchdog@1c007000 (mediatek,mt6983-wdt / mediatek,mt6589-wdt)
  * MMIO      : 0x1c007000, size 0x1000
  * reboot-mode syscon child, register 0x24 (syscon-reboot-mode)
  * HW timeout range 1..32 s; recommended 30 s

Safety contract (enforced in test_lynx_watchdogd.py):
  * Default mode is OFFLINE SIMULATION: `--validate FIXTURE` runs the complete
    petting loop, health gates, and signal handling in-process from hermetic
    JSON.  No hardware is contacted and /dev/watchdog is never opened.
  * Live petting requires BOTH flags `--live --allow-live` and is bounded
    (max cycles, pet interval, optional wall-clock cap).
  * Before every pet: pre-petting health gate — free RAM > 50 MB, rootfs
    writable, 1-min load average < 16.0.  On gate failure the daemon STOPS
    petting and closes WITHOUT the magic 'V' so the hardware watchdog fires
    and performs the safe recovery.
  * SIGTERM / SIGINT: write magic 'V' to /dev/watchdog, close, exit cleanly
    (administrative stop without reset).
  * Every write to /dev/watchdog lives in the whitelisted `_live_*` functions.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# --- Verified hardware facts (B27 doc / mt6983 DTS) -------------------------
EXPECTED_NODE = "watchdog@1c007000"
EXPECTED_COMPATIBLES = ("mediatek,mt6983-wdt", "mediatek,mt6589-wdt")
EXPECTED_BASE = "0x1c007000"
EXPECTED_SIZE = "0x1000"
EXPECTED_REBOOT_OFFSET = "0x24"
EXPECTED_REBOOT_MODE_COMPAT = "syscon-reboot-mode"

WATCHDOG_TIMEOUT_MIN_S = 1
WATCHDOG_TIMEOUT_MAX_S = 32
WATCHDOG_TIMEOUT_RECOMMENDED_S = 30

WATCHDOG_DEVICE = "/dev/watchdog"
MAGIC_STOP_CHAR = "V"

# Pre-petting health gate thresholds (queue D25).
HEALTH_MIN_FREE_RAM_MB = 50.0
HEALTH_MAX_LOADAVG_1M = 16.0

PET_INTERVAL_DEFAULT_S = 5.0
DEFAULT_STATE_FILE = "/tmp/lynx_watchdog_state.json"

# Final states (offline simulation and live daemon alike).
STATE_COMPLETED = "COMPLETED"
STATE_STOPPED_BY_MAGIC_V = "STOPPED_BY_MAGIC_V"
STATE_ABORTED_HEALTH_GATE = "ABORTED_HEALTH_GATE"
STATE_LIVE_TIMEOUT = "LIVE_WALL_TIMEOUT"
VALID_STATES = (
    STATE_COMPLETED,
    STATE_STOPPED_BY_MAGIC_V,
    STATE_ABORTED_HEALTH_GATE,
    STATE_LIVE_TIMEOUT,
)


@dataclass
class SpecError:
    reasons: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.reasons

    def add(self, reason: str) -> None:
        self.reasons.append(reason)


@dataclass
class HealthReport:
    ok: bool
    reasons: List[str]
    details: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {"ok": self.ok, "reasons": self.reasons, "details": self.details}


@dataclass
class PetPlan:
    timeout_s: int
    interval_s: float
    max_cycles: int
    magic: str


@dataclass
class SimulationResult:
    final_state: str
    cycles_patted: int
    transcript: List[Dict[str, Any]]
    last_health: Optional[HealthReport]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "final_state": self.final_state,
            "cycles_patted": self.cycles_patted,
            "transcript": self.transcript,
            "last_health": self.last_health.to_dict() if self.last_health else None,
        }


def validate_watchdogd_spec(doc: Any) -> SpecError:
    """Validate the daemon spec section of an offline fixture."""
    err = SpecError()
    if not isinstance(doc, dict):
        return SpecError(["fixture is not a JSON object"])
    wd = doc.get("watchdog")
    if not isinstance(wd, dict):
        return SpecError(["missing 'watchdog' spec section"])
    if wd.get("node") != EXPECTED_NODE:
        err.add(f"watchdog.node must be {EXPECTED_NODE!r}")
    if wd.get("compatible") not in EXPECTED_COMPATIBLES:
        err.add(f"watchdog.compatible must be one of {EXPECTED_COMPATIBLES}")
    if wd.get("base") != EXPECTED_BASE:
        err.add(f"watchdog.base must be {EXPECTED_BASE!r}")
    if wd.get("size") != EXPECTED_SIZE:
        err.add(f"watchdog.size must be {EXPECTED_SIZE!r}")
    if wd.get("reboot_mode_offset") != EXPECTED_REBOOT_OFFSET:
        err.add(f"watchdog.reboot_mode_offset must be {EXPECTED_REBOOT_OFFSET!r}")
    if wd.get("reboot_mode_compatible") != EXPECTED_REBOOT_MODE_COMPAT:
        err.add(
            "watchdog.reboot_mode_compatible must be "
            f"{EXPECTED_REBOOT_MODE_COMPAT!r}"
        )
    timeout = wd.get("timeout_s")
    if (
        not isinstance(timeout, int)
        or isinstance(timeout, bool)
        or not (WATCHDOG_TIMEOUT_MIN_S <= timeout <= WATCHDOG_TIMEOUT_MAX_S)
    ):
        err.add(
            f"watchdog.timeout_s must be an int in "
            f"[{WATCHDOG_TIMEOUT_MIN_S}, {WATCHDOG_TIMEOUT_MAX_S}]"
        )

    pet = doc.get("petting")
    if not isinstance(pet, dict):
        return SpecError([*err.reasons, "missing 'petting' section"])
    interval = pet.get("interval_s")
    if (
        not isinstance(interval, (int, float))
        or isinstance(interval, bool)
        or not (0 < interval <= WATCHDOG_TIMEOUT_RECOMMENDED_S / 3)
    ):
        err.add(
            "petting.interval_s must be a number in (0, "
            f"{WATCHDOG_TIMEOUT_RECOMMENDED_S / 3}] (keep >=3 pets within the "
            f"{WATCHDOG_TIMEOUT_RECOMMENDED_S}s window)"
        )
    cycles = pet.get("max_cycles")
    if not isinstance(cycles, int) or isinstance(cycles, bool) or cycles < 0:
        err.add("petting.max_cycles must be a non-negative int (0 = unbounded)")
    if pet.get("magic", MAGIC_STOP_CHAR) != MAGIC_STOP_CHAR:
        err.add(f"petting.magic must be {MAGIC_STOP_CHAR!r}")
    return err


def make_pet_plan(doc: Dict[str, Any]) -> PetPlan:
    pet = doc["petting"]
    return PetPlan(
        timeout_s=int(doc["watchdog"]["timeout_s"]),
        interval_s=float(pet["interval_s"]),
        max_cycles=int(pet["max_cycles"]),
        magic=str(pet.get("magic", MAGIC_STOP_CHAR)),
    )


def evaluate_health(probe: Any) -> HealthReport:
    """Pre-petting health gate (queue D25). Pure; probe comes from JSON or /proc."""
    if not isinstance(probe, dict):
        return HealthReport(False, ["health probe is not a JSON object"], {})
    reasons: List[str] = []
    free_mb = probe.get("free_ram_mb")
    if not isinstance(free_mb, (int, float)) or isinstance(free_mb, bool) or free_mb <= HEALTH_MIN_FREE_RAM_MB:
        reasons.append(f"free_ram_mb {free_mb!r} is not > {HEALTH_MIN_FREE_RAM_MB}")
    writable = probe.get("rootfs_writable")
    if writable is not True:
        reasons.append(f"rootfs_writable is {writable!r}, expected true")
    load1 = probe.get("loadavg_1m")
    if not isinstance(load1, (int, float)) or isinstance(load1, bool) or load1 >= HEALTH_MAX_LOADAVG_1M:
        reasons.append(f"loadavg_1m {load1!r} is not < {HEALTH_MAX_LOADAVG_1M}")
    return HealthReport(not reasons, reasons, dict(probe))


def simulate_pet_loop(plan: PetPlan, doc: Dict[str, Any]) -> SimulationResult:
    """Deterministic offline pet loop: health gates, pets, magic-V signal stop."""
    probes: List[Any] = list(doc.get("health_probes") or [])
    if not probes:
        probes = [{"free_ram_mb": 1024.0, "rootfs_writable": True, "loadavg_1m": 1.0}]
    signal_spec = doc.get("signal")
    signal_cycle = None
    if isinstance(signal_spec, dict):
        if signal_spec.get("kind") not in ("SIGTERM", "SIGINT"):
            raise ValueError(f"signal.kind must be SIGTERM or SIGINT: {signal_spec!r}")
        signal_cycle = int(signal_spec.get("at_cycle", 1))
    if plan.max_cycles == 0 and signal_cycle is None:
        raise ValueError(
            "offline simulation requires bounded petting.max_cycles or a signal stop "
            "(unbounded daemon mode is live-only)"
        )

    transcript: List[Dict[str, Any]] = []
    cycles_patted = 0
    last_health: Optional[HealthReport] = None
    final_state = STATE_COMPLETED
    unbounded = plan.max_cycles == 0
    limit = plan.max_cycles if not unbounded else (signal_cycle or 1)

    cycle = 1
    while unbounded or cycle <= limit:
        if signal_cycle == cycle:
            transcript.append(
                {"cycle": cycle, "event": "signal", "action": f"write {plan.magic!r}, close"}
            )
            final_state = STATE_STOPPED_BY_MAGIC_V
            break
        probe = probes[min(cycle - 1, len(probes) - 1)]
        health = evaluate_health(probe)
        last_health = health
        transcript.append({"cycle": cycle, "event": "health", **health.to_dict()})
        if not health.ok:
            transcript.append(
                {
                    "cycle": cycle,
                    "event": "gate-fail",
                    "action": "stop petting; close WITHOUT magic V (hardware watchdog recovery)",
                }
            )
            final_state = STATE_ABORTED_HEALTH_GATE
            break
        transcript.append({"cycle": cycle, "event": "pet", "action": "write '1' (pet)"})
        cycles_patted += 1
        if not unbounded and cycle >= limit:
            break
        cycle += 1

    return SimulationResult(final_state, cycles_patted, transcript, last_health)


def run_offline(fixture_path: Path, state_file: Optional[Path]) -> int:
    """Offline simulation entry point. Returns process exit code."""
    raw = fixture_path.read_text(encoding="utf-8")
    try:
        doc = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"FAIL: fixture is not valid JSON: {exc}", file=sys.stderr)
        return 1
    spec_err = validate_watchdogd_spec(doc)
    if not spec_err.ok:
        print(f"FAIL: MALFORMED_SPEC: {spec_err.reasons}", file=sys.stderr)
        return 1
    plan = make_pet_plan(doc)
    try:
        result = simulate_pet_loop(plan, doc)
    except ValueError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    expected = doc.get("expected_state")
    report = {
        "mode": "offline-simulation",
        "fixture": str(fixture_path),
        "spec_valid": True,
        **result.to_dict(),
        "expected_state": expected,
    }
    if expected not in VALID_STATES:
        print(f"FAIL: expected_state {expected!r} is not one of {VALID_STATES}", file=sys.stderr)
        return 1
    if result.final_state != expected:
        report["verdict"] = "MISMATCH"
        print(
            f"FAIL: final_state {result.final_state!r} != expected {expected!r}",
            file=sys.stderr,
        )
        if state_file is not None:
            state_file.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        return 1
    report["verdict"] = "PASS"
    out = json.dumps(report, indent=2)
    if state_file is not None:
        state_file.write_text(out + "\n", encoding="utf-8")
    print(out)
    return 0


def collect_live_health() -> HealthReport:
    """Read-only /proc probes for the live pre-pet gate (no writes, no device open)."""
    free_mb: float
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            if line.startswith("MemAvailable:"):
                free_mb = int(line.split()[1]) / 1024.0
                break
        else:
            raise LookupError("MemAvailable not found")
    except (OSError, LookupError, ValueError):
        free_mb = 0.0
    load1: float
    try:
        load1 = float(Path("/proc/loadavg").read_text(encoding="utf-8").split()[0])
    except (OSError, ValueError, IndexError):
        load1 = 99.0
    return evaluate_health(
        {"free_ram_mb": free_mb, "rootfs_writable": os.access("/", os.W_OK), "loadavg_1m": load1}
    )


def _live_open_watchdog() -> int:
    """Open /dev/watchdog for petting. Only called under --live --allow-live."""
    return os.open(WATCHDOG_DEVICE, os.O_WRONLY | os.O_CLOEXEC)


def _live_magic_stop(fd: int) -> None:
    """Write magic 'V' then close — administrative stop without hardware reset."""
    os.write(fd, MAGIC_STOP_CHAR.encode("ascii"))
    os.close(fd)


_STOP_REQUESTED = False


def _install_stop_handlers(fd_box: List[Optional[int]]) -> None:
    def _on_signal(signum: int, _frame: Any) -> None:
        global _STOP_REQUESTED
        _STOP_REQUESTED = True
        fd = fd_box[0]
        if fd is not None:
            _live_magic_stop(fd)
            fd_box[0] = None

    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)


def run_live(max_cycles: int, interval_s: float, state_file: Optional[Path], wall_cap_s: float) -> int:
    """Bounded live petting. Every device write is in the whitelisted _live_* fns."""
    if interval_s <= 0 or not (0 < interval_s <= WATCHDOG_TIMEOUT_RECOMMENDED_S / 3):
        print(f"FAIL: pet interval {interval_s}s outside safe window", file=sys.stderr)
        return 1
    fd_box: List[Optional[int]] = [None]
    _install_stop_handlers(fd_box)
    transcript: List[Dict[str, Any]] = []
    cycles_patted = 0
    final_state = STATE_COMPLETED
    start = time.monotonic()
    try:
        fd_box[0] = _live_open_watchdog()
    except OSError as exc:
        print(f"FAIL: cannot open {WATCHDOG_DEVICE}: {exc}", file=sys.stderr)
        return 1
    try:
        cycle = 1
        while max_cycles == 0 or cycle <= max_cycles:
            if wall_cap_s > 0 and (time.monotonic() - start) >= wall_cap_s:
                final_state = STATE_LIVE_TIMEOUT
                break
            health = collect_live_health()
            transcript.append({"cycle": cycle, "event": "health", **health.to_dict()})
            if not health.ok:
                final_state = STATE_ABORTED_HEALTH_GATE
                transcript.append(
                    {
                        "cycle": cycle,
                        "event": "gate-fail",
                        "action": "stop petting; close WITHOUT magic V (hardware watchdog recovery)",
                    }
                )
                break
            os.write(fd_box[0], b"1")
            cycles_patted += 1
            transcript.append({"cycle": cycle, "event": "pet", "action": "write '1' (pet)"})
            if max_cycles and cycle >= max_cycles:
                break
            cycle += 1
            time.sleep(interval_s)
        if fd_box[0] is not None:
            _live_magic_stop(fd_box[0])
            fd_box[0] = None
            transcript.append({"event": "stop", "action": f"write {MAGIC_STOP_CHAR!r}, close"})
    finally:
        if fd_box[0] is not None:
            os.close(fd_box[0])
            fd_box[0] = None
    report = {
        "mode": "live",
        "final_state": final_state,
        "cycles_patted": cycles_patted,
        "transcript": transcript,
    }
    out = json.dumps(report, indent=2)
    if state_file is not None:
        state_file.write_text(out + "\n", encoding="utf-8")
    print(out)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lynx-watchdogd",
        description="Lynx MT6983 TOPRGU hardware watchdog petting/supervision daemon (D25).",
    )
    parser.add_argument("--validate", type=str, metavar="FIXTURE", help="Run offline simulation against FIXTURE JSON")
    parser.add_argument("--live", action="store_true", help="Run live petting (requires --allow-live)")
    parser.add_argument("--allow-live", action="store_true", help="Explicit authorization for live petting")
    parser.add_argument("--cycles", type=int, default=0, help="Max pet cycles; 0 = unbounded daemon mode")
    parser.add_argument("--interval", type=float, default=PET_INTERVAL_DEFAULT_S, help="Seconds between pets")
    parser.add_argument("--wall-cap", type=float, default=0.0, help="Live-only wall-clock cap in seconds; 0 = none")
    parser.add_argument("--state-file", type=str, default=DEFAULT_STATE_FILE, help="Where to write the state JSON report")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.validate and not args.live:
        parser.print_help()
        return 2
    if args.live and not args.allow_live:
        print("REFUSED: live petting requires BOTH --live and --allow-live", file=sys.stderr)
        return 2
    if args.validate:
        state_file = Path(args.state_file) if args.state_file else None
        return run_offline(Path(args.validate), state_file)
    return run_live(args.cycles, args.interval, Path(args.state_file) if args.state_file else None, args.wall_cap)


if __name__ == "__main__":
    sys.exit(main())
