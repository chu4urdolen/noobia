#!/usr/bin/env python3
"""Offline trend & anomaly evaluator for saved portable-health/1 documents.

Solo Dushich round-6 item D16 (Banshee queue, LYNX-ROUND-6-QUEUE-BANSHEE-
20261121.md). Extends the pairwise diff (D10, ``portable_health_diff.py``)
to a *multi-snapshot* series: given an ordered series of >= 2 saved
``portable-health/1`` documents — either **snapshots** (``captured_at`` +
``facts`` + ``machine``) or **evaluated reports** (``captured_at`` +
``checks[]``) — evaluate four trend families:

  1. battery drain velocity (%/hr; mV/hr when voltage is present),
  2. monotonic storage accumulation (free MiB falling / used % rising),
  3. Xid error progression and recurring gauge/fault counters,
  4. thermal drift towards warning/failure bands.

Guarantees (house style for agent tools):
  * pure and offline: reads only the given files; never contacts a machine,
    never spawns a process, never reads the wall clock (rates use the
    documents' own ``captured_at`` timestamps only);
  * bounded: at most 64 documents, 512 KiB each, 256 metric points;
  * missing data never becomes ok: a metric absent from every document is
    ``absent``; a present metric without 2 usable timed points is
    ``insufficient`` — never extrapolated, never ``ok``;
  * concise UTF-8 on stdout (text by default, JSON with ``--json``).

Verdict: the worst rank among *assessable* metrics (ok/warn/fail); when no
metric is assessable the verdict is ``insufficient``.

Exit codes: 0 = healthy trends, 1 = warning trends, 2 = critical
degradation, 3 = insufficient or malformed data, 4 = usage error.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = "portable-health/1"
MAX_DOCS = 64
MAX_DOC_BYTES = 512 * 1024
MAX_POINTS = 256

# Documented, conservative trend bands (per D16 spec). Single-snapshot
# verdict bands remain with the portable-health board itself.
BATTERY_PCT_PER_HR = {"warn": 10.0, "fail": 25.0}      # abnormal discharge
BATTERY_MV_PER_HR = {"warn": 30.0, "fail": 80.0}
STORAGE_TOTAL_MIB = {"warn": 500.0, "fail": 2048.0}    # over the whole series
STORAGE_RATE_MIB_PER_HR = {"warn": 200.0, "fail": 1024.0}
STORAGE_USED_PCT_RISE = {"warn": 5.0}
XID_STEP = {"warn": 1, "fail": 2}                       # between two captures
XID_SERIES = {"warn": 2, "fail": 5}                     # over the whole series
GAUGE_ERRORS_TOTAL = {"warn": 1, "fail": 3}
THERMAL_DRIFT_C_PER_HR = {"warn": 3.0, "fail": 8.0}
THERMAL_GENERIC = {"warn": 45.0, "fail": 60.0}          # generic device band
THERMAL_GPU = {"warn": 85.0, "fail": 95.0}              # RTX GPU band (Aigel-agreed)

_RANK = {"ok": 0, "warn": 1, "fail": 2}


class TrendError(ValueError):
    """Raised on malformed documents or bound violations."""


# ------------------------------------------------------------------ core ---


def _num(value):
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _parse_ts(value):
    if not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _extract_points(doc: dict, metric: str):
    """Pull (timestamp, value) points for one metric from one document.

    Accepts both snapshot shape (facts/machine) and evaluated-report shape
    (checks[].evidence). Returns a list — usually 0 or 1 points.
    """
    ts = _parse_ts(doc.get("captured_at"))
    ts_out = ts.isoformat() if ts else None
    points = []

    def add(value):
        v = _num(value)
        if v is not None:
            points.append({"at": ts_out, "value": v})

    facts = doc.get("facts")
    if isinstance(facts, dict):
        if metric == "battery_capacity_pct":
            add((facts.get("battery") or {}).get("capacity_percent"))
        elif metric == "battery_voltage_mv":
            add((facts.get("battery") or {}).get("voltage_mv"))
        elif metric == "storage_free_mib":
            add((facts.get("storage") or {}).get("free_mib"))
        elif metric == "storage_used_pct":
            add((facts.get("storage") or {}).get("used_percent"))
        elif metric == "thermal_max_c":
            add((facts.get("thermal") or {}).get("max_c"))
        elif metric == "gauge_read_errors":
            add((facts.get("battery") or {}).get("gauge_read_errors"))
    machine = doc.get("machine")
    if isinstance(machine, dict):
        nexus = machine.get("nexus") or {}
        if metric == "xid_count":
            add(nexus.get("xid_count"))
        elif metric == "gpu_temp_c":
            add(nexus.get("temp_c"))
    # evaluated-report shape: evidence of the named check
    checks = doc.get("checks")
    if isinstance(checks, list):
        want = {
            "battery_capacity_pct": ("battery", ("capacity_percent",)),
            "battery_voltage_mv": ("battery", ("voltage_mv",)),
            "storage_free_mib": ("storage", ("free_mib",)),
            "storage_used_pct": ("storage", ("used_percent",)),
            "thermal_max_c": ("thermal", ("max_c",)),
            "xid_count": ("nexus/gpu", ("xid_count",)),
            "gpu_temp_c": ("nexus/gpu", ("temp_c",)),
        }.get(metric)
        if want:
            name, keys = want
            for check in checks:
                if isinstance(check, dict) and check.get("name") == name:
                    ev = check.get("evidence") or {}
                    for k in keys:
                        if ev.get(k) is not None:
                            add(ev.get(k))
                            break
    return points


def _series(docs, metric):
    points = []
    for doc in docs:
        points.extend(_extract_points(doc, metric))
    if len(points) > MAX_POINTS:
        raise TrendError(f"metric {metric!r} has {len(points)} points; bound {MAX_POINTS}")
    return points


def _rate(points):
    """Linear first->last rate over usable time; None when underdetermined."""
    timed = [(p["at"], p["value"]) for p in points if p.get("at")]
    if len(timed) < 2:
        return None
    t0, t1 = _parse_ts(timed[0][0]), _parse_ts(timed[-1][0])
    if t1 is None or t0 is None or t1 <= t0:
        return None
    hours = (t1 - t0).total_seconds() / 3600.0
    return (timed[-1][1] - timed[0][1]) / hours


def _band(value, bands):
    if value is None:
        return "insufficient"
    if value >= bands["fail"]:
        return "fail"
    if value >= bands["warn"]:
        return "warn"
    return "ok"


def _status_from_rate(value, bands):
    if value is None:
        return "insufficient"
    magnitude = abs(value)
    if magnitude >= bands["fail"]:
        return "fail"
    if magnitude >= bands["warn"]:
        return "warn"
    return "ok"


def _values(points):
    return [p["value"] for p in points]


def _monotonic(vals, direction):
    """direction 'fall': strictly decreasing at every step; 'rise': increasing."""
    if len(vals) < 2:
        return False
    if direction == "fall":
        return all(b < a for a, b in zip(vals, vals[1:]))
    return all(b > a for a, b in zip(vals, vals[1:]))


def _worst(*statuses):
    ranked = [s for s in statuses if s in _RANK]
    if not ranked:
        return "ok"
    return max(ranked, key=_RANK.get)


def evaluate_series(docs):
    """Pure series -> trend report. No I/O, no clock reads."""
    if len(docs) < 2:
        raise TrendError("need at least 2 documents for a trend; got %d" % len(docs))
    if len(docs) > MAX_DOCS:
        raise TrendError("series has %d documents; bound %d" % (len(docs), MAX_DOCS))

    # Validate every document up front (fail fast, bounded).
    for i, doc in enumerate(docs):
        if not isinstance(doc, dict):
            raise TrendError(f"doc[{i}] is not a JSON object")
        if doc.get("schema") != SCHEMA:
            raise TrendError(
                f"doc[{i}]: unsupported schema {doc.get('schema')!r}; expected {SCHEMA!r}"
            )
        if not (isinstance(doc.get("facts"), dict)
                or isinstance(doc.get("checks"), list)
                or isinstance(doc.get("machine"), dict)):
            raise TrendError(
                f"doc[{i}]: no usable shape (facts dict, checks list, or machine dict)")

    result = {"schema": "portable-health-trend/1", "docs": len(docs), "metrics": {}}
    assessable = []

    def record(name, status, detail=None, **extra):
        merged = dict(detail or {})
        merged.update(extra)
        result["metrics"][name] = {"status": status, **merged}
        if status in _RANK:
            assessable.append(status)

    # 1. battery drain velocity ------------------------------------------
    cap = _series(docs, "battery_capacity_pct")
    mv = _series(docs, "battery_voltage_mv")
    if not cap and not mv:
        record("battery_drain", "absent", note="no battery capacity or voltage in any document")
    else:
        cap_rate = _rate(cap) if len(cap) >= 2 else None
        mv_rate = _rate(mv) if len(mv) >= 2 else None
        detail = {
            "capacity_points": len(cap),
            "voltage_points": len(mv),
            "capacity_pct_per_hr": cap_rate,
            "voltage_mv_per_hr": mv_rate,
        }
        if cap_rate is None and mv_rate is None:
            status = "insufficient"
            detail["note"] = "no usable time delta between captures"
        else:
            status = "ok"
            if cap_rate is not None:
                s = _status_from_rate(cap_rate, BATTERY_PCT_PER_HR)
                detail["capacity_pct_per_hr_status"] = s
                status = _worst(status, s)
            if mv_rate is not None:
                s = _status_from_rate(mv_rate, BATTERY_MV_PER_HR)
                detail["voltage_mv_per_hr_status"] = s
                status = _worst(status, s)
        record("battery_drain", status, detail)

    # 2. storage accumulation ---------------------------------------------
    free = _series(docs, "storage_free_mib")
    used = _series(docs, "storage_used_pct")
    if not free and not used:
        record("storage", "absent", note="no storage facts in any document")
    elif len(free) < 2 and len(used) < 2:
        record("storage", "insufficient", note="fewer than 2 storage points across the series")
    else:
        detail = {"free_points": len(free), "used_points": len(used)}
        status = "ok"
        if len(free) >= 2 and _monotonic(_values(free), "fall"):
            total_drop = free[0]["value"] - free[-1]["value"]
            rate = _rate(free)
            detail["monotonic_fall_mib"] = total_drop
            detail["fall_rate_mib_per_hr"] = rate
            s = _band(total_drop, STORAGE_TOTAL_MIB)
            detail["total_drop_status"] = s
            status = _worst(status, s)
            if rate is not None:
                s2 = _status_from_rate(rate, STORAGE_RATE_MIB_PER_HR)
                detail["rate_status"] = s2
                status = _worst(status, s2)
        elif len(used) >= 2 and _monotonic(_values(used), "rise"):
            rise = used[-1]["value"] - used[0]["value"]
            detail["used_pct_rise"] = rise
            s = "warn" if rise >= STORAGE_USED_PCT_RISE["warn"] else "ok"
            detail["rise_status"] = s
            status = _worst(status, s)
        else:
            detail["note"] = "no monotonic accumulation across the series"
        record("storage", status, detail)

    # 3. xid / recurring fault counters -------------------------------------
    xid = _series(docs, "xid_count")
    gauge = _series(docs, "gauge_read_errors")
    if not xid and not gauge:
        record("fault_counters", "absent",
               note="no xid or gauge-error counters in any document")
    elif len(xid) < 2 and len(gauge) < 2:
        record("fault_counters", "insufficient",
               note="fewer than 2 counter points across the series")
    else:
        detail = {"xid_points": len(xid), "gauge_points": len(gauge)}
        status = "ok"
        if len(xid) >= 2:
            steps = [b - a for a, b in zip(_values(xid), _values(xid)[1:])]
            max_step = max(steps)
            total = xid[-1]["value"] - xid[0]["value"]
            detail["xid_max_step"] = max_step
            detail["xid_total_delta"] = total
            if max_step >= XID_STEP["fail"] or total >= XID_SERIES["fail"]:
                s = "fail"
            elif max_step >= XID_STEP["warn"] or total >= XID_SERIES["warn"]:
                s = "warn"
            else:
                s = "ok"
            detail["xid_status"] = s
            status = _worst(status, s)
        if len(gauge) >= 2:
            rise = gauge[-1]["value"] - gauge[0]["value"]
            detail["gauge_error_rise"] = rise
            s = _band(rise, GAUGE_ERRORS_TOTAL)
            detail["gauge_status"] = s
            status = _worst(status, s)
        record("fault_counters", status, detail)

    # 4. thermal drift -------------------------------------------------------
    therm = _series(docs, "thermal_max_c")
    gpu = _series(docs, "gpu_temp_c")
    if not therm and not gpu:
        record("thermal", "absent", note="no thermal facts in any document")
    elif len(therm) < 2 and len(gpu) < 2:
        record("thermal", "insufficient",
               note="fewer than 2 thermal points across the series")
    else:
        detail = {"device_points": len(therm), "gpu_points": len(gpu)}
        status = "ok"
        if len(therm) >= 2:
            drift = _rate(therm)
            last = therm[-1]["value"]
            detail["drift_c_per_hr"] = drift
            detail["last_max_c"] = last
            s1 = _status_from_rate(drift, THERMAL_DRIFT_C_PER_HR) if drift is not None else "ok"
            s2 = _band(last, THERMAL_GENERIC)
            detail["drift_status"] = s1
            detail["level_status"] = s2
            status = _worst(status, s1, s2)
        if len(gpu) >= 2:
            last = gpu[-1]["value"]
            detail["gpu_last_c"] = last
            s = _band(last, THERMAL_GPU)
            detail["gpu_level_status"] = s
            status = _worst(status, s)
        record("thermal", status, detail)

    result["verdict"] = _worst(*assessable) if assessable else "insufficient"
    return result


# ------------------------------------------------------------------ load ---


def load_doc(path: str) -> dict | list:
    p = Path(path)
    try:
        size = p.stat().st_size
    except OSError as exc:
        raise TrendError(f"cannot stat {p}: {exc}")
    if size > MAX_DOC_BYTES:
        raise TrendError(f"{p}: {size} bytes exceed bound {MAX_DOC_BYTES}")
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TrendError(f"{p}: unreadable or invalid JSON: {exc}")
    if not isinstance(doc, (dict, list)):
        raise TrendError(f"{p}: top level must be a JSON object or array")
    return doc


def load_series(paths):
    docs = []
    for path in paths:
        doc = load_doc(path)
        if isinstance(doc, list):
            if len(doc) > MAX_DOCS:
                raise TrendError(f"{path}: array has {len(doc)} documents; bound {MAX_DOCS}")
            docs.extend(doc)
        else:
            docs.append(doc)
    return docs


# ----------------------------------------------------------------- output ---


def format_report(rep: dict) -> str:
    lines = [
        f"portable-health-trend/1 — {rep['docs']} document(s), verdict: {rep['verdict'].upper()}"
    ]
    for name in ("battery_drain", "storage", "fault_counters", "thermal"):
        m = rep["metrics"].get(name)
        if not m:
            continue
        lines.append(f"  {name:<16} {m['status']}")
        for k, v in m.items():
            if k == "status":
                continue
            lines.append(f"      {k}: {v!r}")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Offline trend & anomaly evaluator for saved portable-health/1 documents."
    )
    ap.add_argument("paths", nargs="*", help="ordered saved documents (or one JSON array file)")
    ap.add_argument("--json", action="store_true", help="emit JSON instead of text")
    args = ap.parse_args(argv)

    if not args.paths:
        print("error: give at least two documents (ordered), or one JSON array file", file=sys.stderr)
        return 4

    try:
        docs = load_series(args.paths)
        rep = evaluate_series(docs)
    except TrendError as exc:
        print(f"trend: {exc}", file=sys.stderr)
        return 3

    if args.json:
        print(json.dumps(rep, indent=2, sort_keys=True))
    else:
        print(format_report(rep))
    return {"ok": 0, "warn": 1, "fail": 2, "insufficient": 3}.get(rep["verdict"], 3)


if __name__ == "__main__":
    sys.exit(main())
