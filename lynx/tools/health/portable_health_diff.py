#!/usr/bin/env python3
"""Offline diff of two saved portable-health/1 reports.

Solo Dushich round-5 item D10 (Gwyn queue, note #148). Given two *saved*
evaluator reports (``portable_health.evaluate`` output: ``schema``,
``host``, ``verdict``, ``checks[]``), produce a bounded, compact diff:

  * checks whose status changed (before -> after),
  * new unknowns (known before, unknown after),
  * resolved unknowns (unknown before, known after),
  * checks added or removed between reports,
  * verdict change.

Guarantees (house style for agent tools):
  * pure and offline: reads only the two given files, never contacts a
    machine, never spawns a process, no periodic job;
  * bounded: input files are size-capped (512 KiB default), the number of
    checks per report is capped (256 default) so output stays bounded;
  * concise UTF-8 on stdout: compact text by default, JSON with ``--json``;
  * exit codes: 0 = diff computed (regardless of whether anything changed),
    2 = usage error, 4 = invalid report (schema, shape, or bounds).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCHEMA = "portable-health/1"
MAX_REPORT_BYTES = 512 * 1024
MAX_CHECKS = 256
KNOWN_STATUSES = {"ok", "warn", "fail", "unknown"}


class ReportError(ValueError):
    """Raised when a saved report is invalid, malformed, or over bounds."""


# ------------------------------------------------------------------ core ---


def _check_checks(report: dict, label: str) -> dict:
    schema = report.get("schema")
    if schema != SCHEMA:
        raise ReportError(
            f"{label}: unsupported schema {schema!r}; expected {SCHEMA!r}"
        )
    checks = report.get("checks")
    if not isinstance(checks, list):
        raise ReportError(f"{label}: 'checks' must be a list")
    if len(checks) > MAX_CHECKS:
        raise ReportError(f"{label}: {len(checks)} checks exceed bound {MAX_CHECKS}")
    for i, check in enumerate(checks):
        if not isinstance(check, dict) or "name" not in check or "status" not in check:
            raise ReportError(f"{label}: checks[{i}] lacks 'name' and 'status'")
        if check["status"] not in KNOWN_STATUSES:
            raise ReportError(
                f"{label}: checks[{i}] ({check.get('name')!r}) has "
                f"unrecognised status {check['status']!r}"
            )
    return report


def diff_reports(before: dict, after: dict) -> dict:
    """Pure diff of two validated report dicts. No I/O, no clock reads."""
    _check_checks(before, "before")
    _check_checks(after, "after")

    before_by_name = {c["name"]: c for c in before["checks"]}
    after_by_name = {c["name"]: c for c in after["checks"]}

    changes = []
    for name in sorted(set(before_by_name) | set(after_by_name)):
        b = before_by_name.get(name)
        a = after_by_name.get(name)
        if b is None or a is None or b["status"] != a["status"]:
            changes.append({
                "name": name,
                "scope": (a or b).get("scope"),
                "before": b["status"] if b else None,
                "after": a["status"] if a else None,
            })

    new_unknowns = [c["name"] for c in changes
                    if c["before"] in KNOWN_STATUSES and c["after"] == "unknown"]
    resolved_unknowns = [c["name"] for c in changes
                         if c["before"] == "unknown" and c["after"] in KNOWN_STATUSES]

    verdict_before = before.get("verdict")
    verdict_after = after.get("verdict")
    unchanged = sum(1 for name, c in before_by_name.items()
                    if name in after_by_name and after_by_name[name]["status"] == c["status"])

    return {
        "schema": SCHEMA,
        "host": after.get("host") or before.get("host"),
        "verdict": {
            "before": verdict_before,
            "after": verdict_after,
            "changed": verdict_before != verdict_after,
        },
        "status_changes": changes,
        "new_unknowns": new_unknowns,
        "resolved_unknowns": resolved_unknowns,
        "unchanged": unchanged,
        "changed": bool(changes) or verdict_before != verdict_after,
    }


# ----------------------------------------------------------------- loading ---


def load_report(path: Path, max_bytes: int = MAX_REPORT_BYTES) -> dict:
    """Read one saved report with a hard size cap and strict JSON parsing."""
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise ReportError(f"cannot stat {path}: {exc.strerror or exc}") from None
    if size > max_bytes:
        raise ReportError(f"{path}: {size} bytes exceed bound {max_bytes}")
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ReportError(f"cannot read {path}: {exc}") from None
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ReportError(f"{path}: invalid JSON ({exc.msg} at line {exc.lineno})") from None
    if not isinstance(data, dict):
        raise ReportError(f"{path}: top-level JSON must be an object")
    return data


# ------------------------------------------------------------------- text ---


def format_text(diff: dict) -> str:
    v = diff["verdict"]
    lines = [
        f"{diff.get('host') or '?'}: verdict {v['before']} -> {v['after']}"
        + ("" if v["changed"] else " (unchanged)"),
        (
            f"changed {len(diff['status_changes'])}, "
            f"new-unknowns {len(diff['new_unknowns'])}, "
            f"resolved-unknowns {len(diff['resolved_unknowns'])}, "
            f"unchanged {diff['unchanged']}"
        ),
    ]
    for c in diff["status_changes"]:
        before = c["before"] if c["before"] is not None else "(absent)"
        after = c["after"] if c["after"] is not None else "(absent)"
        lines.append(f"  - {c['name']}: {before} -> {after}")
    return "\n".join(lines)


# -------------------------------------------------------------------- cli ---


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Diff two saved portable-health/1 reports (offline, bounded)."
    )
    parser.add_argument("before", type=Path, help="earlier saved report JSON file")
    parser.add_argument("after", type=Path, help="later saved report JSON file")
    parser.add_argument("--max-bytes", type=int, default=MAX_REPORT_BYTES,
                        help=f"per-report size cap in bytes (default {MAX_REPORT_BYTES})")
    parser.add_argument("--json", action="store_true", help="print JSON instead of text")
    args = parser.parse_args(argv)

    # A diff needs two saved reports; require two existing file paths.
    if not (args.before.is_file() and args.after.is_file()):
        parser.error("both reports must be existing file paths")

    def load(path: Path) -> dict:
        try:
            return load_report(path, max_bytes=args.max_bytes)
        except ReportError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return None

    before = load(args.before)
    after = load(args.after)
    if before is None or after is None:
        return 4

    try:
        diff = diff_reports(before, after)
    except ReportError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 4

    if args.json:
        print(json.dumps(diff, indent=2))
    else:
        print(format_text(diff))
    return 0


if __name__ == "__main__":
    sys.exit(main())
