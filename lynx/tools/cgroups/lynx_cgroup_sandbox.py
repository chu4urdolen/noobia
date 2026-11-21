#!/usr/bin/env python3
"""lynx_cgroup_sandbox — Lynx (OnePlus Nord 3 / MT6983) cgroups v2 agent sandbox.

Round 8 item D27 (queue: LYNX-ROUND-8-QUEUE-BANSHEE-20261121.md).
Establishes the cgroups v2 resource controller specification that limits the
autonomous agent's memory and CPU consumption, so an agent loop can never
OOM-kill the system network stack or starve the survival/watchdog daemons.

Verified on-disk contract (B32 architecture doc, section 5,
`lynx/linux-port/docs/LYNX-AUTONOMY-ARCHITECTURE-20261121.md`):
  * /sys/fs/cgroup/lynx-agent/  memory.max  536870912 (512 MiB)
                                memory.high 419430400 (400 MiB)
                                cpu.max     150000 100000 (1.5 cores)
                                memory.oom.group 1

Safety contract (enforced in test_lynx_cgroup_sandbox.py):
  * Default mode is OFFLINE SIMULATION: `--validate FIXTURE` validates the
    spec, plans the full mutation sequence, and evaluates a hermetic
    pressure-stress series in-process. Zero hardware contact.
  * Live mode requires BOTH `--live` and `--allow-live`; it performs a
    bounded READ-ONLY inspection of /sys/fs/cgroup (v2 root, controllers,
    the lynx-agent group's limits and PSI files). It never writes anything.
  * All mutations are SIMULATED data records (SimulatedAction), never
    executed: ensure_group, memory.max, memory.high, cpu.max,
    memory.oom.group, cgroup.procs PID migration.
  * No `os` import at all; no exec; no destructive tokens (enforced by the
    safety-boundary tests).
  * Status broker: /tmp state file (spec, plan, polls, severity); path is a single constant.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

# --- B32 architecture parameters (mirrored; keep in sync with the arch doc)
CGROUP_ROOT = "/sys/fs/cgroup"
DEFAULT_CGROUP_NAME = "lynx-agent"
DEFAULT_MEMORY_MAX_BYTES = 536870912   # 512 MiB hard ceiling
DEFAULT_MEMORY_HIGH_BYTES = 419430400  # 400 MiB throttle threshold
DEFAULT_CPU_QUOTA_US = 150000          # cpu.max "150000 100000"
DEFAULT_CPU_PERIOD_US = 100000
DEFAULT_OOM_GROUP = "1"

# --- Design bounds (documented; not from hardware docs)
MEMORY_MAX_MIN_BYTES = 16 * 1024 ** 2
MEMORY_MAX_MAX_BYTES = 4 * 1024 ** 3
MEMORY_HIGH_MIN_BYTES = 1 * 1024 ** 2
CPU_US_MIN = 1000
CPU_US_MAX = 1_000_000
MAX_QUOTA_PERIOD_RATIO = 4.0           # an agent may not be granted > 4 cores

# --- PSI thrash thresholds (design, documented; ms of delay per second)
THRASH_MEMORY_SOME_AVG3_MS = 10.0
THRASH_CPU_SOME_AVG3_MS = 25.0
ELEVATED_MEMORY_SOME_AVG3_MS = 5.0
ELEVATED_CPU_SOME_AVG3_MS = 12.5

SEVERITY_OK = "OK"
SEVERITY_ELEVATED = "ELEVATED"
SEVERITY_THRASHING = "THRASHING"
SEVERITIES = (SEVERITY_OK, SEVERITY_ELEVATED, SEVERITY_THRASHING)

DEFAULT_STATE_FILE = "/tmp/lynx_cgroup_state.json"

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


class SpecError(ValueError):
    """Spec or fixture validation failure; carries all collected reasons."""

    def __init__(self, reasons: List[str]):
        super().__init__("; ".join(reasons))
        self.reasons = reasons


class PressureParseError(ValueError):
    """PSI (pressure-stress) file content is malformed."""


@dataclass
class SandboxSpec:
    cgroup_name: str
    memory_max_bytes: int
    memory_high_bytes: int
    cpu_quota_us: int
    cpu_period_us: int
    oom_group: str
    target_pid: Optional[int]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cgroup_name": self.cgroup_name,
            "memory_max_bytes": self.memory_max_bytes,
            "memory_high_bytes": self.memory_high_bytes,
            "cpu_quota_us": self.cpu_quota_us,
            "cpu_period_us": self.cpu_period_us,
            "oom_group": self.oom_group,
            "target_pid": self.target_pid,
        }


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
class PressureReading:
    kind: str
    some_avg3: float
    some_avg60: float
    some_avg300: float
    some_total: float
    full_avg3: float
    full_avg60: float
    full_avg300: float
    full_total: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "some": {"avg3": self.some_avg3, "avg60": self.some_avg60,
                     "avg300": self.some_avg300, "total": self.some_total},
            "full": {"avg3": self.full_avg3, "avg60": self.full_avg60,
                     "avg300": self.full_avg300, "total": self.full_total},
        }


@dataclass
class ThrashAssessment:
    severity: str
    memory_thrashing: bool
    cpu_thrashing: bool
    reasons: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "severity": self.severity,
            "memory_thrashing": self.memory_thrashing,
            "cpu_thrashing": self.cpu_thrashing,
            "reasons": self.reasons,
        }


def _bounded_int(doc: Dict[str, Any], key: str, default: int,
                 lo: int, hi: Optional[int], reasons: List[str]) -> int:
    if key not in doc:
        return default
    val = doc[key]
    if isinstance(val, bool) or not isinstance(val, int):
        reasons.append(f"{key} must be an integer")
        return default
    if hi is not None and not (lo <= val <= hi):
        upper = str(hi) if hi is not None else "unbounded"
        reasons.append(f"{key}={val} outside [{lo}, {upper}]")
        return default
    return val


def build_spec(spec_doc: Any) -> SandboxSpec:
    """Fill defaults and validate a cgroup sandbox spec. Raises SpecError."""
    reasons: List[str] = []
    if not isinstance(spec_doc, dict):
        raise SpecError(["spec must be a JSON object"])
    doc = spec_doc

    name = doc.get("cgroup_name", DEFAULT_CGROUP_NAME)
    if not isinstance(name, str) or not NAME_RE.fullmatch(name):
        reasons.append("cgroup_name must match [a-z0-9][a-z0-9_-]* (lowercase, no path chars)")
        name = DEFAULT_CGROUP_NAME

    mem_max = _bounded_int(doc, "memory_max_bytes", DEFAULT_MEMORY_MAX_BYTES,
                           MEMORY_MAX_MIN_BYTES, MEMORY_MAX_MAX_BYTES, reasons)
    mem_high = _bounded_int(doc, "memory_high_bytes", DEFAULT_MEMORY_HIGH_BYTES,
                            MEMORY_HIGH_MIN_BYTES, None, reasons)
    if mem_high >= mem_max:
        reasons.append("memory_high_bytes must be strictly less than memory_max_bytes")
    quota = _bounded_int(doc, "cpu_quota_us", DEFAULT_CPU_QUOTA_US,
                         CPU_US_MIN, CPU_US_MAX, reasons)
    period = _bounded_int(doc, "cpu_period_us", DEFAULT_CPU_PERIOD_US,
                          CPU_US_MIN, CPU_US_MAX, reasons)
    if quota > MAX_QUOTA_PERIOD_RATIO * period:
        reasons.append(
            f"cpu_quota_us={quota} exceeds {MAX_QUOTA_PERIOD_RATIO} x cpu_period_us={period}")

    oom = doc.get("oom_group", DEFAULT_OOM_GROUP)
    if oom not in ("0", "1"):
        reasons.append("oom_group must be '0' or '1'")
        oom = DEFAULT_OOM_GROUP

    pid = doc.get("target_pid", None)
    if pid is not None and (isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0):
        reasons.append("target_pid must be a positive integer or null")
        pid = None

    if reasons:
        raise SpecError(reasons)
    return SandboxSpec(name, mem_max, mem_high, quota, period, oom, pid)


def plan_actions(spec: SandboxSpec) -> List[SimulatedAction]:
    """Deterministic SIMULATED mutation plan for the cgroup (order matters)."""
    root = f"{CGROUP_ROOT}/{spec.cgroup_name}"
    actions = [
        SimulatedAction("ensure_group", root, {"op": "mkdir", "mode": 0o755}),
        SimulatedAction("set_property", f"{root}/memory.max",
                        {"value": str(spec.memory_max_bytes)}),
        SimulatedAction("set_property", f"{root}/memory.high",
                        {"value": str(spec.memory_high_bytes)}),
        SimulatedAction("set_property", f"{root}/cpu.max",
                        {"value": f"{spec.cpu_quota_us} {spec.cpu_period_us}"}),
        SimulatedAction("set_property", f"{root}/memory.oom.group",
                        {"value": spec.oom_group}),
    ]
    if spec.target_pid is not None:
        actions.append(SimulatedAction("migrate_pid", f"{root}/cgroup.procs",
                                       {"pid": spec.target_pid,
                                        "note": "migrate only after limits are set"}))
    return actions


def parse_pressure(text: Any, kind: str = "psi") -> PressureReading:
    """Parse a cgroup PSI file (some/full lines). Raises PressureParseError."""
    if not isinstance(text, str):
        raise PressureParseError(f"{kind}: pressure content must be a string")
    got: Dict[str, Dict[str, float]] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        tokens = line.split()
        if len(tokens) < 2 or tokens[0] not in ("some", "full"):
            raise PressureParseError(f"{kind}: unrecognized line {line!r}")
        which = tokens[0]
        rest = tokens[1:]
        if len(rest) != 4:
            raise PressureParseError(
                f"{kind}: expected 4 'name=value' fields after {which!r}, got {len(rest)}")
        pairs: Dict[str, float] = {}
        for tok in rest:
            if "=" not in tok:
                raise PressureParseError(f"{kind}: expected name=value field, got {tok!r}")
            key, _, rawval = tok.partition("=")
            if key not in ("avg3", "avg60", "avg300", "total") or key in pairs:
                raise PressureParseError(f"{kind}: bad or duplicate field {key!r}")
            try:
                val = float(rawval)
            except ValueError:
                raise PressureParseError(f"{kind}: non-numeric value in {tok!r}")
            if val < 0:
                raise PressureParseError(f"{kind}: negative value in {tok!r}")
            pairs[key] = val
        for required in ("avg3", "avg60", "avg300", "total"):
            if required not in pairs:
                raise PressureParseError(f"{kind}: {which} line missing {required}")
        got[which] = pairs
    for required in ("some", "full"):
        if required not in got:
            raise PressureParseError(f"{kind}: missing {required!r} line")
    return PressureReading(
        kind=kind,
        some_avg3=got["some"]["avg3"], some_avg60=got["some"]["avg60"],
        some_avg300=got["some"]["avg300"], some_total=got["some"]["total"],
        full_avg3=got["full"]["avg3"], full_avg60=got["full"]["avg60"],
        full_avg300=got["full"]["avg300"], full_total=got["full"]["total"],
    )


def assess_thrash(memory: PressureReading, cpu: PressureReading) -> ThrashAssessment:
    """Classify PSI some-avg3 pressure into OK / ELEVATED / THRASHING."""
    mem_flag = memory.some_avg3 >= THRASH_MEMORY_SOME_AVG3_MS
    cpu_flag = cpu.some_avg3 >= THRASH_CPU_SOME_AVG3_MS
    if mem_flag or cpu_flag:
        severity = SEVERITY_THRASHING
    elif memory.some_avg3 >= ELEVATED_MEMORY_SOME_AVG3_MS or cpu.some_avg3 >= ELEVATED_CPU_SOME_AVG3_MS:
        severity = SEVERITY_ELEVATED
    else:
        severity = SEVERITY_OK
    reasons: List[str] = []
    if mem_flag:
        reasons.append(
            f"memory PSI some avg3 {memory.some_avg3} ms/s >= {THRASH_MEMORY_SOME_AVG3_MS} ms/s (thrash)")
    if cpu_flag:
        reasons.append(
            f"cpu PSI some avg3 {cpu.some_avg3} ms/s >= {THRASH_CPU_SOME_AVG3_MS} ms/s (thrash)")
    if not mem_flag and not cpu_flag and severity == SEVERITY_ELEVATED:
        reasons.append(
            f"PSI some avg3 in elevated band (memory {memory.some_avg3}, cpu {cpu.some_avg3} ms/s)")
    if not reasons:
        reasons.append(
            f"PSI some avg3 within nominal band (memory {memory.some_avg3}, cpu {cpu.some_avg3} ms/s)")
    return ThrashAssessment(severity, mem_flag, cpu_flag, reasons)


def validate_fixture(doc: Any) -> str:
    """Structural fixture checks. Returns the expected mode. Raises SpecError."""
    if not isinstance(doc, dict):
        raise SpecError(["fixture must be a JSON object"])
    if not isinstance(doc.get("platform"), str) or not doc["platform"].strip():
        raise SpecError(["platform must be a non-empty string"])
    if "spec" in doc and doc["spec"] is not None and not isinstance(doc["spec"], dict):
        raise SpecError(["spec must be a JSON object or null"])
    expect = doc.get("expect", "plan")
    if expect not in ("plan", "spec_rejected"):
        raise SpecError(["expect must be 'plan' or 'spec_rejected'"])
    series = doc.get("pressure_series", [])
    if expect == "plan":
        if not isinstance(series, list) or not series:
            raise SpecError(["pressure_series must be a non-empty list"])
        for i, entry in enumerate(series, 1):
            if not isinstance(entry, dict):
                raise SpecError([f"pressure_series[{i}] must be an object"])
            for key in ("memory", "cpu", "expected_severity"):
                if key not in entry:
                    raise SpecError([f"pressure_series[{i}] missing {key!r}"])
            if entry["expected_severity"] not in SEVERITIES:
                raise SpecError([f"pressure_series[{i}] expected_severity must be one of {SEVERITIES}"])
    return expect


def publish_state(path: Path, report: Dict[str, Any]) -> None:
    """Status broker: publish current sandbox state (readers poll this file)."""
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


def run_offline(fixture_path: Path, state_file: Path) -> int:
    try:
        doc = json.loads(fixture_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"FAIL: fixture is not valid JSON: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"FAIL: cannot read fixture: {exc}", file=sys.stderr)
        return 1
    try:
        expect = validate_fixture(doc)
    except SpecError as exc:
        print(f"FAIL: MALFORMED_FIXTURE: {exc.reasons}", file=sys.stderr)
        return 1

    if expect == "spec_rejected":
        try:
            build_spec(doc.get("spec", {}))
        except SpecError as exc:
            needle = doc.get("expected_error_contains")
            if needle and not any(needle in reason for reason in exc.reasons):
                print(f"FAIL: expected an error mentioning {needle!r}; got {exc.reasons}",
                      file=sys.stderr)
                return 1
            report = {"mode": "offline", "state": "SPEC_REJECTED",
                      "reasons": exc.reasons, "timestamp": time.time()}
            publish_state(state_file, report)
            print(json.dumps(report, indent=2))
            return 0
        print("FAIL: fixture expected spec_rejected but the spec validated", file=sys.stderr)
        return 1

    try:
        spec = build_spec(doc.get("spec", {}))
        plan = plan_actions(spec)
        if "expected_actions" in doc:
            want = doc["expected_actions"]
            got = [a.action for a in plan]
            if got != want:
                raise SpecError([f"plan actions {got} != expected {want}"])
    except SpecError as exc:
        print(f"FAIL: MALFORMED_SPEC: {exc.reasons}", file=sys.stderr)
        return 1

    polls: List[Dict[str, Any]] = []
    try:
        for i, entry in enumerate(doc["pressure_series"], 1):
            memory = parse_pressure(entry["memory"], f"poll{i}-memory")
            cpu = parse_pressure(entry["cpu"], f"poll{i}-cpu")
            assessment = assess_thrash(memory, cpu)
            if assessment.severity != entry["expected_severity"]:
                raise SpecError([
                    f"poll {i}: severity {assessment.severity!r} != "
                    f"expected {entry['expected_severity']!r}"])
            polls.append({"poll": i, "memory_some_avg3": memory.some_avg3,
                          "cpu_some_avg3": cpu.some_avg3,
                          "assessment": assessment.to_dict()})
    except PressureParseError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    except SpecError as exc:
        print(f"FAIL: SEVERITY_MISMATCH: {exc.reasons}", file=sys.stderr)
        return 1

    report = {
        "mode": "offline",
        "state": "VALIDATED",
        "spec": spec.to_dict(),
        "plan": [a.to_dict() for a in plan],
        "polls": polls,
        "final_severity": polls[-1]["assessment"]["severity"],
        "timestamp": time.time(),
    }
    publish_state(state_file, report)
    print(json.dumps(report, indent=2))
    return 0


def run_live(state_file: Path) -> int:
    """Bounded READ-ONLY inspection of the cgroup v2 root. Writes nothing."""
    details: Dict[str, Any] = {"v2_root": False,
                              "note": f"{CGROUP_ROOT}/cgroup.controllers not readable; "
                                     f"cgroup v2 unified root not present"}
    agent: Dict[str, Any] = {"present": False}
    root = Path(CGROUP_ROOT)
    try:
        controllers = (root / "cgroup.controllers").read_text(encoding="utf-8",
                                                               errors="replace").split()
        subtree = (root / "cgroup.subtree_control").read_text(encoding="utf-8",
                                                              errors="replace").split()
        details = {"v2_root": True, "controllers": controllers,
                   "subtree_control": subtree}
    except OSError:
        pass
    if details.get("v2_root"):
        agent_dir = root / DEFAULT_CGROUP_NAME
        for prop in ("memory.max", "memory.high", "cpu.max", "memory.oom.group"):
            try:
                agent[prop] = (agent_dir / prop).read_text(encoding="utf-8",
                                                           errors="replace").strip()
            except OSError:
                agent[prop] = None
        agent["present"] = agent.get("memory.max") is not None
        for psi in ("memory.pressure", "cpu.pressure"):
            try:
                text = (agent_dir / psi).read_text(encoding="utf-8", errors="replace")
            except OSError:
                agent[psi] = None
                continue
            kind = "memory" if psi.startswith("memory") else "cpu"
            try:
                agent[psi] = parse_pressure(text, kind).to_dict()
            except PressureParseError as exc:
                agent[psi] = {"parse_error": str(exc)}
    default_spec = build_spec({})
    report = {
        "mode": "live-inspect",
        "state": "INSPECTED",
        "cgroup_root": CGROUP_ROOT,
        "details": details,
        "agent": agent,
        "proposed_plan": [a.to_dict() for a in plan_actions(default_spec)],
        "timestamp": time.time(),
    }
    publish_state(state_file, report)
    print(json.dumps(report, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lynx-cgroup-sandbox",
        description="Lynx cgroups v2 agent sandbox planner (D27, B32 parameters).",
    )
    parser.add_argument("--validate", type=str, metavar="FIXTURE",
                        help="Run offline validation/plan/PSI evaluation against FIXTURE JSON")
    parser.add_argument("--live", action="store_true",
                        help="Run read-only live inspection (requires --allow-live)")
    parser.add_argument("--allow-live", action="store_true",
                        help="Explicit authorization for live inspection")
    parser.add_argument("--state-file", type=str, default=DEFAULT_STATE_FILE,
                        help="Status broker state file")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.validate and not args.live:
        parser.print_help()
        return 2
    if args.live and not args.allow_live:
        print("REFUSED: live inspection requires BOTH --live and --allow-live", file=sys.stderr)
        return 2
    state_file = Path(args.state_file)
    if args.validate:
        return run_offline(Path(args.validate), state_file)
    return run_live(state_file)


if __name__ == "__main__":
    sys.exit(main())
