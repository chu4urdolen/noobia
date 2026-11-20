#!/usr/bin/env python3
"""Portable passive health board for Noobia machines.

Solo Dushich's first Lynx deliverable (team handoff 2026-11-21). Inspired by
Aigel's vitals board: a compact, one-glance verdict over machine state, but
designed to be *portable*:

  * The core is a pure function. It evaluates a captured **snapshot**
    (JSON of observed facts) and never touches the network, never reads a
    live device, and never spawns a process. That makes it runnable offline
    anywhere — on Nexus, on Lynx, or in a test — with fixture input.
  * **Common checks** (battery, thermal, storage, network, services) are
    machine-agnostic. A per-host **profile** selects which apply: Lynx
    declares a battery, a desktop does not.
  * **Machine-specific checks** (Lynx modem MD1 state and agent queue;
    Nexus GPU, RAM, SMART) live in a separate section of the snapshot and a
    separate registry, so the common set stays clean and reusable.
  * A check that cannot find the facts it needs reports ``unknown``.
    Missing data never becomes ``ok``.

Thresholds are conservative and documented per check; the Lynx battery band
honors the installed reserve guard (power off at 20%, even while charging)
and the "recheck before trials" band seen in the handoff history.

Verdict ranks: fail > warn > ok; ``unknown`` checks are listed but do not
drive the verdict unless every check is unknown.

Exit codes: 0 = ok, 1 = warn, 2 = fail, 3 = all checks unknown,
4 = invalid snapshot or schema.

Prototype status: reviewed by Aria before anything is installed on a device.
This tool installs nothing and contacts nothing.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone

SCHEMA = "portable-health/1"

_RANK = {"ok": 0, "warn": 1, "fail": 2}

# --------------------------------------------------------------- helpers ---


def _num(value):
    """Accept ints/floats (not bools, not numeric strings); else None."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _result(name: str, scope: str, status: str, evidence=None, notes=None):
    return {
        "name": name,
        "scope": scope,
        "status": status,
        "evidence": evidence or {},
        "notes": notes or [],
    }


def _worst(*statuses):
    return max((s for s in statuses if s in _RANK), key=_RANK.get, default=None)


# ------------------------------------------------- common (portable) ---


def check_battery(facts: dict) -> dict:
    """Battery capacity against the Lynx reserve-guard band.

    The installed guard can power Lynx off at 20% even while charging, so
    below 20% is fail and 20-35% is the trial-recheck band (warn). Gauge
    read errors degrade the evidence and force at least a warn.
    """
    facts = facts or {}
    cap = _num(facts.get("capacity_percent"))
    errors = _num(facts.get("gauge_read_errors"))
    charging = facts.get("charging")
    current = _num(facts.get("current_ma"))
    if cap is None and errors is None:
        return _result("battery", "common", "unknown", {}, ["no battery facts in snapshot"])
    evidence = {}
    if cap is not None:
        evidence["capacity_percent"] = cap
    if errors is not None:
        evidence["gauge_read_errors"] = int(errors)
    if charging is not None:
        evidence["charging"] = charging
    if current is not None:
        evidence["current_ma"] = int(current)
    notes = []
    if cap is None:
        status = "unknown"
        notes.append("capacity missing; cannot judge reserve band")
    elif cap < 20.0:
        status = "fail"
        notes.append("capacity below 20%: reserve guard may power off (fires even while charging)")
    elif cap < 35.0:
        status = "warn"
        notes.append("capacity in 20-35% trial-recheck band")
        if charging is False:
            notes.append("discharging; reserve guard may power off at 20%")
    else:
        status = "ok"
    if errors is not None and errors > 0:
        if status == "ok":
            status = "warn"
        notes.append("gauge read errors present; battery evidence degraded")
    return _result("battery", "common", status, evidence, notes)


def check_thermal(facts: dict) -> dict:
    """Highest reported temperature; warn >= 43 C, fail >= 50 C.

    A throttled flag outranks an otherwise cool reading: the machine is
    already throttling itself, which is a live guard condition.
    """
    facts = facts or {}
    temp = _num(facts.get("max_c"))
    throttled = facts.get("throttled") is True
    if temp is None:
        return _result("thermal", "common", "unknown",
                       {"throttled": throttled}, ["no thermal facts in snapshot"])
    evidence = {"max_c": temp}
    if throttled:
        evidence["throttled"] = True
    notes = []
    if temp >= 50.0:
        status = "fail"
        notes.append(f"max {temp} C >= 50 C")
    elif temp >= 43.0:
        status = "warn"
        notes.append(f"max {temp} C >= 43 C")
    else:
        status = "ok"
    if throttled and status == "ok":
        status = "warn"
    if throttled:
        notes.append("thermal throttling reported")
    return _result("thermal", "common", status, evidence, notes)


def check_storage(facts: dict) -> dict:
    """Root filesystem: used percent, free MiB, and filesystem errors.

    Errors are fail regardless of space. Space bands: used >= 95% or free
    < 128 MiB is fail; used >= 85% or free < 512 MiB is warn. Whichever of
    used/free is present is judged; both are judged if both are present.
    """
    facts = facts or {}
    used = _num(facts.get("used_percent"))
    free = _num(facts.get("free_mib"))
    errors = _num(facts.get("fs_errors"))
    if used is None and free is None and errors is None:
        return _result("storage", "common", "unknown", {}, ["no storage facts in snapshot"])
    evidence = {}
    if used is not None:
        evidence["used_percent"] = used
    if free is not None:
        evidence["free_mib"] = int(free)
    if errors is not None:
        evidence["fs_errors"] = int(errors)
    notes = []
    status = "ok"
    if errors is not None and errors > 0:
        status = "fail"
        notes.append(f"filesystem errors reported: {int(errors)}")
    if used is not None:
        if used >= 95.0:
            status = _worst(status, "fail") or "fail"
            notes.append(f"root used {used}% (>= 95%)")
        elif used >= 85.0:
            status = _worst(status, "warn") or "warn"
            notes.append(f"root used {used}% (>= 85%)")
    elif free is not None:
        if free < 128.0:
            status = _worst(status, "fail") or "fail"
            notes.append(f"root free {int(free)} MiB (< 128)")
        elif free < 512.0:
            status = _worst(status, "warn") or "warn"
            notes.append(f"root free {int(free)} MiB (< 512)")
    return _result("storage", "common", status, evidence, notes)


def check_network(facts: dict) -> dict:
    """Link state by transport: wifi, usb gadget, or none.

    Wi-Fi: no carrier is fail; carrier without IPv4 is warn (DHCP may be
    pending); carrier + IPv4 is ok. USB gadget: IPv4 is the success signal;
    absence is warn, not fail — the ACM gadget may simply not be enumerated
    yet on the host. ``none`` is fail.
    """
    facts = facts or {}
    link = facts.get("link_state")
    carrier = facts.get("carrier")
    ipv4 = facts.get("ipv4")
    if link is None:
        return _result("network", "common", "unknown",
                       {"carrier": carrier, "ipv4": bool(ipv4) if ipv4 else None},
                       ["no link_state in snapshot"])
    evidence = {"link_state": link, "ipv4": bool(ipv4) if ipv4 else None}
    if carrier is not None:
        evidence["carrier"] = carrier
    if link == "none":
        return _result("network", "common", "fail", evidence, ["link state reported none"])
    if link == "wifi":
        if carrier is False:
            return _result("network", "common", "fail", evidence, ["Wi-Fi link up but no carrier"])
        if carrier is True and ipv4:
            return _result("network", "common", "ok", evidence, [])
        if carrier is True:
            return _result("network", "common", "warn", evidence, ["Wi-Fi carrier without IPv4 (DHCP pending?)"])
        return _result("network", "common", "unknown", evidence, ["Wi-Fi carrier not reported"])
    if link == "usb":
        if ipv4:
            return _result("network", "common", "ok", evidence, ["USB gadget link with IPv4"])
        return _result("network", "common", "warn", evidence, ["USB link without IPv4 (host may not have enumerated the gadget yet)"])
    return _result("network", "common", "unknown", evidence, [f"unrecognized link_state {link!r}"])


def check_services(facts: dict) -> dict:
    """Declared required services: all running and none failed is ok.

    An empty required list is unknown, not ok: the snapshot simply did not
    declare what must be up, and absence of a list proves nothing.
    """
    facts = facts or {}
    required = [str(s) for s in (facts.get("required") or [])]
    running = [str(s) for s in (facts.get("running") or [])]
    failed = [str(s) for s in (facts.get("failed") or [])]
    if not required:
        return _result("services", "common", "unknown",
                       {"running": running, "failed": failed},
                       ["no required services declared in snapshot"])
    missing = [s for s in required if s not in running]
    evidence = {"required": required, "missing": missing, "failed": failed}
    if missing or failed:
        notes = []
        if missing:
            notes.append("required services not running: " + ", ".join(missing))
        if failed:
            notes.append("services reported failed: " + ", ".join(failed))
        return _result("services", "common", "fail", evidence, notes)
    return _result("services", "common", "ok", evidence, [])


COMMON_CHECKS = {
    "battery": check_battery,
    "thermal": check_thermal,
    "storage": check_storage,
    "network": check_network,
    "services": check_services,
}

# ------------------------------------------------- machine-specific ---


def lynx_modem(machine: dict) -> dict:
    """MD1 state under the no-SIM policy: expected 0 (idle).

    Nonzero is warn, not fail: a supervised trial may legitimately move it,
    and the SIM stays out until Aria's attended test is ready.
    """
    machine = machine or {}
    md1 = _num(machine.get("modem_md1_state"))
    if md1 is None:
        return _result("lynx_modem", "machine", "unknown", {}, ["no modem_md1_state in snapshot"])
    evidence = {"modem_md1_state": int(md1)}
    if md1 == 0:
        return _result("lynx_modem", "machine", "ok", evidence, ["MD1 idle, matches no-SIM policy"])
    return _result("lynx_modem", "machine", "warn", evidence,
                   [f"MD1 state {int(md1)} nonzero; confirm an authorized supervised trial is in progress"])


def lynx_agent_queue(machine: dict) -> dict:
    """Agent queue liveness: counts are ok; a very old pending job is warn."""
    machine = machine or {}
    pending = _num(machine.get("pending"))
    running = _num(machine.get("running"))
    oldest = _num(machine.get("oldest_pending_seconds"))
    if pending is None and running is None and oldest is None:
        return _result("lynx_agent_queue", "machine", "unknown", {}, ["no agent queue facts in snapshot"])
    evidence = {}
    for key, value in (("pending", pending), ("running", running), ("oldest_pending_seconds", oldest)):
        if value is not None:
            evidence[key] = int(value)
    if oldest is not None and oldest > 1800.0:
        return _result("lynx_agent_queue", "machine", "warn", evidence,
                       [f"oldest pending job waiting {int(oldest)} s (> 1800)"])
    return _result("lynx_agent_queue", "machine", "ok", evidence, [])


def nexus_gpu(machine: dict) -> dict:
    """GPU health (Nexus profile only). Warn >= 85 C, fail >= 95 C.

    Xid events force at least warn; uncorrectable ECC is fail. Thresholds
    mirror Aigel's board so the two boards agree on the same machine.
    """
    machine = machine or {}
    temp = _num(machine.get("temp_c"))
    xid = _num(machine.get("xid_count"))
    ecc = _num(machine.get("ecc_uncorrectable"))
    if temp is None and xid is None and ecc is None:
        return _result("nexus_gpu", "machine", "unknown", {}, ["no GPU facts in snapshot"])
    evidence = {}
    for key, value in (("temp_c", temp), ("xid_count", xid), ("ecc_uncorrectable", ecc)):
        if value is not None:
            evidence[key] = int(value)
    notes = []
    status = "ok"
    if temp is not None:
        if temp >= 95.0:
            status = "fail"
            notes.append(f"GPU {temp} C >= 95 C")
        elif temp >= 85.0:
            status = "warn"
            notes.append(f"GPU {temp} C >= 85 C")
    if xid is not None and xid > 0:
        status = _worst(status, "warn")
        notes.append(f"{int(xid)} NVIDIA Xid event(s)")
    if ecc is not None and ecc > 0:
        status = "fail"
        notes.append(f"{int(ecc)} uncorrectable ECC error(s)")
    return _result("nexus_gpu", "machine", status, evidence, notes)


def nexus_ram(machine: dict) -> dict:
    """MemAvailable share: fail < 2%, warn < 10% (Aigel convention)."""
    machine = machine or {}
    pct = _num(machine.get("available_pct"))
    if pct is None:
        return _result("nexus_ram", "machine", "unknown", {}, ["no RAM facts in snapshot"])
    evidence = {"available_pct": pct}
    if pct < 2.0:
        return _result("nexus_ram", "machine", "fail", evidence, [f"MemAvailable {pct}% (< 2%)"])
    if pct < 10.0:
        return _result("nexus_ram", "machine", "warn", evidence, [f"MemAvailable {pct}% (< 10%)"])
    return _result("nexus_ram", "machine", "ok", evidence, [])


def nexus_smart(machine: dict) -> dict:
    """Per-disk SMART overall health; any FAILED device is fail."""
    machine = machine or {}
    failed = [str(d) for d in (machine.get("failed_devices") or [])]
    checked = machine.get("checked")
    if not failed and checked is not None:
        return _result("nexus_smart", "machine", "ok",
                       {"checked": checked, "failed_devices": failed}, [])
    if failed:
        return _result("nexus_smart", "machine", "fail",
                       {"failed_devices": failed},
                       ["SMART overall-health FAILED on: " + ", ".join(failed)])
    return _result("nexus_smart", "machine", "unknown",
                   {"checked": checked, "failed_devices": failed},
                   ["SMART not reported as checked"])


# ------------------------------------------------------------ profiles ---

PROFILES = {
    "lynx": {
        "common": ["battery", "thermal", "storage", "network", "services"],
        "machine": {
            "lynx_modem": lynx_modem,
            "lynx_agent_queue": lynx_agent_queue,
        },
        "machine_source": "lynx",
    },
    "nexus": {
        # Desktop: no battery. GPU/SMART/RAM stay in the machine section,
        # deliberately separate from the common set.
        "common": ["thermal", "storage", "network", "services"],
        "machine": {
            "nexus_gpu": nexus_gpu,
            "nexus_ram": nexus_ram,
            "nexus_smart": nexus_smart,
        },
        "machine_source": "nexus",
    },
}


# -------------------------------------------------------------- engine ---


def _parse_captured_at(value):
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def evaluate(snapshot: dict, max_age_seconds=None, now=None) -> dict:
    """Pure snapshot -> report. No I/O of any kind happens here."""
    if not isinstance(snapshot, dict):
        raise ValueError("snapshot must be a JSON object")
    if snapshot.get("schema") != SCHEMA:
        raise ValueError(f"unsupported schema {snapshot.get('schema')!r}; expected {SCHEMA!r}")
    host = snapshot.get("host")
    profile_name = snapshot.get("profile") or host
    profile = PROFILES.get(profile_name)
    facts = snapshot.get("facts") or {}
    if not isinstance(facts, dict):
        raise ValueError("snapshot.facts must be an object")
    machine_all = snapshot.get("machine") or {}
    if not isinstance(machine_all, dict):
        raise ValueError("snapshot.machine must be an object")

    checks = []
    if profile is None:
        # Unknown host: no profile declares which common checks apply, so we
        # run them all — each is facts-driven and self-limiting (no battery
        # facts simply means the battery check reports unknown, never ok) —
        # and flag the missing profile in its own machine check.
        for name in COMMON_CHECKS:
            checks.append(COMMON_CHECKS[name](facts.get(name) or {}))
        checks.append(_result("profile", "machine", "unknown",
                              {"profile": profile_name},
                              [f"no profile registered for host {profile_name!r}; no machine checks run"]))
    else:
        for name in profile["common"]:
            checks.append(COMMON_CHECKS[name](facts.get(name) or {}))
        machine_facts = machine_all.get(profile["machine_source"]) or {}
        if not isinstance(machine_facts, dict):
            machine_facts = {}
        for name, fn in profile["machine"].items():
            checks.append(fn(machine_facts))

    known = [c for c in checks if c["status"] in _RANK]
    if not known:
        verdict = "unknown"
    else:
        verdict = max((c["status"] for c in known), key=_RANK.get)

    stale = False
    captured_at = snapshot.get("captured_at")
    parsed = _parse_captured_at(captured_at)
    if parsed is not None and max_age_seconds is not None:
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        now_dt = (now or datetime.now(timezone.utc))
        if now_dt.tzinfo is None:
            now_dt = now_dt.replace(tzinfo=timezone.utc)
        age = (now_dt - parsed).total_seconds()
        stale = age > max_age_seconds

    return {
        "schema": SCHEMA,
        "host": host,
        "profile": profile_name,
        "captured_at": captured_at,
        "verdict": verdict,
        "stale": stale,
        "checks": checks,
    }


EXIT_BY_VERDICT = {"ok": 0, "warn": 1, "fail": 2, "unknown": 3}


def format_board(report: dict) -> str:
    """Compact one-glance text, bounded: evidence truncated per line."""
    lines = [
        f"{report.get('host') or '?'} — verdict: {report['verdict']}  "
        f"(captured {report.get('captured_at') or 'unknown'}"
        + (", STALE" if report.get("stale") else "") + ")"
    ]
    for check in report["checks"]:
        detail = "; ".join(check["notes"]) or json.dumps(check["evidence"], sort_keys=True)
        if len(detail) > 96:
            detail = detail[:95] + "…"
        lines.append(f"  {check['status']:<7} {check['name']:<18} {detail}")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate a captured portable-health snapshot (offline, read-only).")
    parser.add_argument("--snapshot", default="-",
                        help="snapshot JSON file, or - for stdin (default)")
    parser.add_argument("--max-age", type=float, default=None, metavar="SECONDS",
                        help="flag the report stale when captured_at is older than this")
    parser.add_argument("--text", action="store_true",
                        help="print the compact text board instead of JSON")
    args = parser.parse_args(argv)

    try:
        if args.snapshot == "-":
            raw = sys.stdin.read()
        else:
            with open(args.snapshot, "r", encoding="utf-8") as handle:
                raw = handle.read()
    except OSError as exc:
        print(f"portable_health: cannot read snapshot: {exc}", file=sys.stderr)
        return 4
    try:
        report = evaluate(json.loads(raw), max_age_seconds=args.max_age)
    except ValueError as exc:
        print(f"portable_health: {exc}", file=sys.stderr)
        return 4
    if args.text:
        print(format_board(report))
    else:
        print(json.dumps(report, indent=2, sort_keys=True))
    return EXIT_BY_VERDICT[report["verdict"]]


if __name__ == "__main__":
    raise SystemExit(main())
