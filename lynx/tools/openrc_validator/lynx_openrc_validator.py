#!/usr/bin/env python3
"""lynx_openrc_validator — Lynx (OnePlus Nord 3 / MT6983) OpenRC service-tree validator.

Round 8 item D28 (queue: LYNX-ROUND-8-QUEUE-BANSHEE-20261121.md).
Offline validator for the untethered-boot service dependency graph on
Alpine Linux:

    bootmisc -> sysfs -> networking -> lynx-watchdogd -> lynx-survivald
              -> lynx-cgroups -> lynx-agent -> lynx-presence

It parses OpenRC dependency directives (`need`, `use`, `before`, `after`)
from service definitions, asserts the startup graph is free of hard
deadlocks, computes a deterministic startup order and the reverse shutdown
order, and flags missing prerequisites.

Dependency semantics (documented, per OpenRC behavior):
  * `need`   : HARD prerequisite. X must be running before S starts and is
               stopped after S. A `need` cycle is a hard DEADLOCK.
  * `use`    : SOFT prerequisite. X should start before S, but S continues
               if X is down, and S never stops X. A `use`-only cycle is a
               note, not a deadlock.
  * `before`/`after` : WEAK ordering only (no start-stop obligation).
               A weak cycle is informational UNLESS the same pair is
               ordered in both directions, which is an ORDER_CONFLICT.

Safety contract (enforced in test_lynx_openrc_validator.py):
  * Default mode is OFFLINE: `--validate FIXTURE` runs the full validation
    on hermetic JSON service definitions. Zero hardware contact.
  * Live mode requires BOTH `--live` and `--allow-live`; it performs a
    bounded READ-ONLY parse of the staged initds that live on disk
    (lynx-watchdogd, lynx-survivald) plus declared external base services.
    It never writes anything, never installs any init script.
  * No `os` import at all; no exec; no destructive tokens (enforced by the
    safety-boundary tests).
  * Status broker: /tmp state file (report: orders, cycles, verdict).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

# --- Service definitions (verified on-disk)
STAGED_INITDS: Tuple[Tuple[str, str], ...] = (
    ("lynx-watchdogd", "../watchdog_daemon/lynx-watchdogd.initd"),
    ("lynx-survivald", "../survival_daemon/lynx-survivald.initd"),
)
KNOWN_EXTERNAL = ("bootmisc", "sysfs", "networking", "net", "loopback", "local")
EXPECTED_CHAIN = (
    "bootmisc", "sysfs", "networking",
    "lynx-watchdogd", "lynx-survivald", "lynx-cgroups",
    "lynx-agent", "lynx-presence",
)

DEFAULT_STATE_FILE = "/tmp/lynx_openrc_state.json"

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
DIRECTIVES = ("need", "use", "before", "after")

VERDICT_PASS = "PASS"
VERDICT_FAIL = "FAIL"


class ParseError(ValueError):
    """OpenRC depend() block or service definition is malformed."""


class SpecError(ValueError):
    """Fixture validation failure; carries all collected reasons."""

    def __init__(self, reasons: List[str]):
        super().__init__("; ".join(reasons))
        self.reasons = reasons


@dataclass
class ServiceDef:
    name: str
    need: Tuple[str, ...] = ()
    use: Tuple[str, ...] = ()
    before: Tuple[str, ...] = ()
    after: Tuple[str, ...] = ()
    provides: Tuple[str, ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "need": list(self.need),
            "use": list(self.use),
            "before": list(self.before),
            "after": list(self.after),
            "provides": list(self.provides),
        }


@dataclass
class ValidationReport:
    services: List[str]
    startup_order: List[str]
    shutdown_order: List[str]
    hard_cycles: List[List[str]]
    order_conflicts: List[List[str]]
    weak_cycles: List[List[str]]
    missing_prerequisites: List[List[str]]
    weak_unknown_refs: List[List[str]]
    verdict: str
    reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "services": self.services,
            "startup_order": self.startup_order,
            "shutdown_order": self.shutdown_order,
            "hard_cycles": self.hard_cycles,
            "order_conflicts": self.order_conflicts,
            "weak_cycles": self.weak_cycles,
            "missing_prerequisites": self.missing_prerequisites,
            "weak_unknown_refs": self.weak_unknown_refs,
            "verdict": self.verdict,
            "reasons": self.reasons,
        }


def _check_name(name: Any, ctx: str) -> str:
    if not isinstance(name, str) or not NAME_RE.fullmatch(name):
        raise ParseError(f"{ctx}: invalid service name {name!r} "
                         f"(must match [a-z0-9][a-z0-9_-]*)")
    return name


def parse_depend_block(text: str, ctx: str = "initd") -> Dict[str, List[str]]:
    """Extract need/use/before/after from an OpenRC depend() block."""
    m = re.search(r"depend\(\)\s*\{", text)
    if m is None:
        raise ParseError(f"{ctx}: no depend() block found")
    rest = text[m.end():]
    end = rest.find("}")
    if end == -1:
        raise ParseError(f"{ctx}: unterminated depend() block")
    block = rest[:end]
    deps: Dict[str, List[str]] = {d: [] for d in (*DIRECTIVES, "provide")}
    for line in block.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        tokens = stripped.split()
        cmd = tokens[0]
        if cmd not in deps:
            raise ParseError(f"{ctx}: unknown depend directive {cmd!r}")
        if len(tokens) < 2:
            raise ParseError(f"{ctx}: directive {cmd!r} without services")
        for svc in tokens[1:]:
            deps[cmd].append(_check_name(svc, f"{ctx}:{cmd}"))
    return deps


def parse_initd(text: str, name: str) -> ServiceDef:
    """Parse one staged OpenRC initd file into a ServiceDef."""
    deps = parse_depend_block(text, ctx=name)
    return ServiceDef(
        name=name,
        need=tuple(deps["need"]),
        use=tuple(deps["use"]),
        before=tuple(deps["before"]),
        after=tuple(deps["after"]),
        provides=tuple(deps["provide"]),
    )


def parse_service_def(doc: Any) -> ServiceDef:
    """Parse one fixture service definition (dict) into a ServiceDef."""
    if not isinstance(doc, dict):
        raise ParseError("service definition must be a JSON object")
    name = _check_name(doc.get("name"), "service.name")
    lists: Dict[str, List[str]] = {}
    for directive in (*DIRECTIVES, "provide"):
        value = doc.get(directive, [])
        if value is None:
            value = []
        if not isinstance(value, list):
            raise ParseError(f"service {name}: {directive} must be a list")
        lists[directive] = [_check_name(s, f"service {name} {directive}") for s in value]
    return ServiceDef(
        name=name,
        need=tuple(lists["need"]),
        use=tuple(lists["use"]),
        before=tuple(lists["before"]),
        after=tuple(lists["after"]),
        provides=tuple(lists["provide"]),
    )


def build_start_edges(services: Dict[str, ServiceDef],
                      provider: Optional[Dict[str, str]] = None) -> List[Tuple[str, str, str]]:
    """Startup order edges (src -> dst, kind): src must start before dst.

    need/use: prerequisite -> prereq first.
    after X  : X first.  before X : this service first.
    A dependency on a name another service `provide`s resolves to the
    provider (that provider must be running).
    """
    provider = provider or {}
    edges: List[Tuple[str, str, str]] = []
    for svc in services.values():
        for x in svc.need:
            edges.append((provider.get(x, x), svc.name, "need"))
        for x in svc.use:
            edges.append((provider.get(x, x), svc.name, "use"))
        for x in svc.after:
            edges.append((provider.get(x, x), svc.name, "weak"))
        for x in svc.before:
            edges.append((svc.name, provider.get(x, x), "weak"))
    return edges


def _strongly_connected(nodes: Sequence[str], adj: Dict[str, List[str]]) -> List[List[str]]:
    """Iterative Tarjan SCC; returns components in deterministic order."""
    index: Dict[str, int] = {}
    lowlink: Dict[str, int] = {}
    on_stack: Dict[str, bool] = {}
    stack: List[str] = []
    counter = [0]
    components: List[List[str]] = []

    for root in sorted(nodes):
        if root in index:
            continue
        work: List[Tuple[str, int]] = [(root, 0)]
        while work:
            node, pi = work[-1]
            if pi == 0:
                index[node] = counter[0]
                lowlink[node] = counter[0]
                counter[0] += 1
                stack.append(node)
                on_stack[node] = True
            recurse = False
            neighbors = adj.get(node, [])
            for i in range(pi, len(neighbors)):
                nb = neighbors[i]
                if nb not in index:
                    work[-1] = (node, i + 1)
                    work.append((nb, 0))
                    recurse = True
                    break
                elif on_stack.get(nb):
                    lowlink[node] = min(lowlink[node], index[nb])
            if recurse:
                continue
            work.pop()
            if work:
                parent = work[-1][0]
                lowlink[parent] = min(lowlink[parent], lowlink[node])
            if lowlink[node] == index[node]:
                comp: List[str] = []
                while True:
                    nb = stack.pop()
                    on_stack[nb] = False
                    comp.append(nb)
                    if nb == node:
                        break
                components.append(sorted(comp))
    return components


def topological_order(nodes: Sequence[str], edges: List[Tuple[str, str, str]]) -> List[str]:
    """Deterministic Kahn order (alphabetical tie-break); cyclic prefix only."""
    nodes_set = set(nodes)
    succ: Dict[str, List[str]] = {n: [] for n in nodes_set}
    indeg: Dict[str, int] = {n: 0 for n in nodes_set}
    for src, dst, _kind in edges:
        if src in nodes_set and dst in nodes_set and src != dst:
            succ[src].append(dst)
            indeg[dst] += 1
    ready = sorted(n for n in nodes_set if indeg[n] == 0)
    order: List[str] = []
    while ready:
        node = ready.pop(0)
        order.append(node)
        for nb in sorted(set(succ[node])):
            indeg[nb] -= 1
            if indeg[nb] == 0:
                ready.append(nb)
        ready.sort()
    return order


def validate_tree(services: Dict[str, ServiceDef], known_external: Sequence[str]) -> ValidationReport:
    """Full offline validation: cycles, orders, missing prerequisites."""
    nodes = set(services) | set(known_external)
    provider: Dict[str, str] = {}
    for name, svc in services.items():
        for prov in svc.provides:
            provider[prov] = name
    edges = build_start_edges(services, provider)
    adj: Dict[str, List[str]] = {n: [] for n in nodes}
    for src, dst, _kind in edges:
        if src in nodes and dst in nodes and src != dst:
            adj[src].append(dst)

    hard_cycles: List[List[str]] = []
    order_conflicts: List[List[str]] = []
    weak_cycles: List[List[str]] = []
    for comp in _strongly_connected(sorted(nodes), adj):
        if len(comp) == 1:
            node = comp[0]
            self_kinds = [kind for s, d, kind in edges if s == node == d]
            if any(kind in ("need", "use") for kind in self_kinds):
                hard_cycles.append(comp)
            elif self_kinds:
                order_conflicts.append(comp)
            continue
        internal = [(s, d, k) for s, d, k in edges if s in comp and d in comp]
        if any(k == "need" for _s, _d, k in internal):
            hard_cycles.append(comp)
            continue
        soft_pairs = {(s, d) for s, d, _k in internal}
        if any((d, s) in soft_pairs for s, d in soft_pairs):
            order_conflicts.append(comp)
        else:
            weak_cycles.append(comp)

    missing: List[List[str]] = []
    weak_unknown: List[List[str]] = []
    for svc in (services[n] for n in sorted(services)):
        for dep in (*svc.need, *svc.use):
            if dep not in nodes and provider.get(dep) not in nodes:
                missing.append([svc.name, dep])
        for dep in (*svc.before, *svc.after):
            if dep not in nodes and provider.get(dep) not in nodes:
                weak_unknown.append([svc.name, dep])

    all_nodes = sorted(nodes)
    startup = topological_order(all_nodes, edges)
    reasons: List[str] = []
    for comp in hard_cycles:
        reasons.append(f"DEADLOCK: need-cycle {comp}")
    for comp in order_conflicts:
        reasons.append(f"ORDER_CONFLICT: contradictory weak ordering in {comp}")
    for svc, dep in missing:
        reasons.append(f"MISSING_PREREQUISITE: {svc} needs/use {dep} (undefined)")
    verdict = VERDICT_FAIL if (hard_cycles or order_conflicts or missing) else VERDICT_PASS
    return ValidationReport(
        services=sorted(services),
        startup_order=startup,
        shutdown_order=list(reversed(startup)),
        hard_cycles=hard_cycles,
        order_conflicts=order_conflicts,
        weak_cycles=weak_cycles,
        missing_prerequisites=missing,
        weak_unknown_refs=weak_unknown,
        verdict=verdict,
        reasons=reasons,
    )


def validate_fixture(doc: Any) -> None:
    """Structural fixture checks. Raises SpecError."""
    reasons: List[str] = []
    if not isinstance(doc, dict):
        raise SpecError(["fixture must be a JSON object"])
    if not isinstance(doc.get("platform"), str) or not doc["platform"].strip():
        reasons.append("platform must be a non-empty string")
    services = doc.get("services")
    if not isinstance(services, list) or not services:
        reasons.append("services must be a non-empty list")
    else:
        names: set = set()
        for i, entry in enumerate(services, 1):
            if not isinstance(entry, dict):
                reasons.append(f"services[{i}] must be an object")
                continue
            if not isinstance(entry.get("name"), str) or not NAME_RE.fullmatch(entry["name"]):
                reasons.append(f"services[{i}].name must match [a-z0-9][a-z0-9_-]*")
            else:
                if entry["name"] in names:
                    reasons.append(f"services[{i}]: duplicate name {entry['name']!r}")
                names.add(entry["name"])
    ext = doc.get("known_external", [])
    if not isinstance(ext, list) or not all(isinstance(s, str) for s in ext):
        reasons.append("known_external must be a list of strings")
    expected = doc.get("expected", {})
    if not isinstance(expected, dict):
        reasons.append("expected must be a JSON object")
    else:
        if expected.get("verdict") not in (VERDICT_PASS, VERDICT_FAIL):
            reasons.append("expected.verdict must be PASS or FAIL")
        chain = expected.get("expected_chain")
        if chain is not None and (not isinstance(chain, list) or not all(isinstance(s, str) for s in chain)):
            reasons.append("expected.expected_chain must be a list of strings")
    if reasons:
        raise SpecError(reasons)


def publish_state(path: Path, report: Dict[str, Any]) -> None:
    """Status broker: publish current validation state (readers poll this file)."""
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


def _subsequence(chain: Sequence[str], order: Sequence[str]) -> bool:
    it = iter(order)
    return all(name in it for name in chain)


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
        validate_fixture(doc)
    except SpecError as exc:
        print(f"FAIL: MALFORMED_FIXTURE: {exc.reasons}", file=sys.stderr)
        return 1

    try:
        services: Dict[str, ServiceDef] = {}
        for entry in doc["services"]:
            svc = parse_service_def(entry)
            services[svc.name] = svc
    except ParseError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    report = validate_tree(services, tuple(doc.get("known_external", [])))
    expected = doc.get("expected", {})
    mismatches: List[str] = []
    if report.verdict != expected.get("verdict"):
        mismatches.append(f"verdict {report.verdict} != expected {expected.get('verdict')}")
    chain = expected.get("expected_chain")
    if chain is not None and not _subsequence(chain, report.startup_order):
        mismatches.append(f"expected_chain {list(chain)} not a subsequence of "
                          f"startup_order {report.startup_order}")
    for comp in report.hard_cycles:
        if expected.get("expect_hard_cycle") and sorted(comp) == sorted(expected["expect_hard_cycle"]):
            break
    else:
        if expected.get("expect_hard_cycle"):
            mismatches.append(f"expected hard cycle {expected['expect_hard_cycle']} "
                              f"among {report.hard_cycles}")
    if expected.get("expect_order_conflict"):
        if not any(sorted(comp) == sorted(expected["expect_order_conflict"])
                   for comp in report.order_conflicts):
            mismatches.append(f"expected order conflict {expected['expect_order_conflict']} "
                              f"among {report.order_conflicts}")
    if expected.get("expect_missing"):
        wanted = {tuple(pair) for pair in expected["expect_missing"]}
        got = {tuple(pair) for pair in report.missing_prerequisites}
        if not wanted.issubset(got):
            mismatches.append(f"expected missing prerequisites {sorted(wanted)} among {sorted(got)}")

    payload = {"mode": "offline", "verdict": report.verdict, "report": report.to_dict(),
               "mismatches": mismatches}
    publish_state(state_file, payload)
    if mismatches:
        print(f"FAIL: {mismatches}", file=sys.stderr)
        print(json.dumps(payload, indent=2))
        return 1
    print(json.dumps(payload, indent=2))
    return 0


def run_live(state_file: Path) -> int:
    """Bounded READ-ONLY parse of the staged initds on disk. Writes nothing."""
    here = Path(__file__).resolve().parent
    services: Dict[str, ServiceDef] = {}
    parsed: List[Dict[str, Any]] = []
    problems: List[str] = []
    for name, rel in STAGED_INITDS:
        path = (here / rel).resolve()
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            problems.append(f"{name}: cannot read {path}: {exc}")
            continue
        try:
            svc = parse_initd(text, name)
        except ParseError as exc:
            problems.append(str(exc))
            continue
        services[svc.name] = svc
        parsed.append({"service": name, "path": str(path), "deps": svc.to_dict()})
    if problems:
        payload = {"mode": "live-inspect", "state": "PROBLEMS", "problems": problems,
                   "parsed": parsed}
        publish_state(state_file, payload)
        print(json.dumps(payload, indent=2), file=sys.stderr)
        return 1
    report = validate_tree(services, KNOWN_EXTERNAL)
    payload = {"mode": "live-inspect", "state": "INSPECTED", "parsed": parsed,
               "report": report.to_dict()}
    publish_state(state_file, payload)
    print(json.dumps(payload, indent=2))
    return 0 if report.verdict == VERDICT_PASS else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lynx-openrc-validator",
        description="Lynx OpenRC service-tree dependency & startup order validator (D28).",
    )
    parser.add_argument("--validate", type=str, metavar="FIXTURE",
                        help="Run offline validation against FIXTURE JSON")
    parser.add_argument("--live", action="store_true",
                        help="Read-only parse of staged initds (requires --allow-live)")
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
