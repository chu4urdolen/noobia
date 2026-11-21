#!/usr/bin/env python3
"""Prioritized implementation map for Lynx's status-only components.

Joins the curated, source-cited ``status_only_map.json`` with the coverage
audit (``lynx_tool_coverage.py``) and an optional saved snapshot. It fails if
the map and the audit disagree about which components are status-only, so
the map cannot go stale silently. For each component it says whether the gap
is a missing agent tool, a needed live trial, a blocked route, or nothing. A
driver that is not loaded on this boot is reported as its own gap, never as a
missing tool.

Never contacts Lynx.

  lynx_status_only_map.py --text         # uses state/latest.json if present
  lynx_status_only_map.py --no-status    # map against the source-only audit
  lynx_status_only_map.py --status FILE  # JSON for a specific snapshot
"""

import argparse
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import lynx_tool_coverage as cov  # noqa: E402
import lynx_tool_manifest as mm  # noqa: E402

MAP_PATH = HERE / "status_only_map.json"
KINDS = ("missing_wrapper", "trial_needed", "blocked", "status_is_function")
FIELDS = {"component", "priority", "kind", "owner", "existing_routes", "missing_tool",
          "companions_needed", "physical_proof_absent", "docs"}


class MapError(Exception):
    pass


def load_map(path=MAP_PATH):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise MapError(f"status-only map unreadable: {exc}") from None
    entries = data.get("components") if isinstance(data, dict) else None
    if not isinstance(entries, list) or not entries:
        raise MapError("status-only map needs a non-empty 'components' list")
    seen, priorities = set(), []
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != FIELDS:
            raise MapError(f"map entry needs exactly {sorted(FIELDS)}")
        name = entry["component"]
        if name in seen:
            raise MapError(f"component listed twice: {name}")
        seen.add(name)
        if entry["kind"] not in KINDS:
            raise MapError(f"{name}: unknown kind {entry['kind']!r}")
        if not isinstance(entry["priority"], int):
            raise MapError(f"{name}: priority must be an integer")
        priorities.append(entry["priority"])
        routes = entry["existing_routes"]
        if not isinstance(routes, list) or not all(
                isinstance(r, dict) and set(r) == {"route", "source"} and
                all(isinstance(r[k], str) and r[k].strip() for k in r) for r in routes):
            raise MapError(f"{name}: each route needs a non-empty route and source")
        if entry["kind"] in ("missing_wrapper", "trial_needed") and not routes:
            raise MapError(f"{name}: kind {entry['kind']} must cite an existing route")
        for key in ("owner", "missing_tool", "companions_needed", "physical_proof_absent"):
            if not isinstance(entry[key], str) or not entry[key].strip():
                raise MapError(f"{name}: {key} must be a non-empty string")
        if not isinstance(entry["docs"], list):
            raise MapError(f"{name}: docs must be a list")
    if sorted(priorities) != list(range(1, len(entries) + 1)):
        raise MapError("priorities must be 1..N with no gaps or repeats")
    return sorted(entries, key=lambda e: e["priority"])


def cited_paths(entries):
    """Repository paths cited by the map (line suffixes removed).

    ``upstream:`` sources name third-party repositories outside Git and are
    excluded; everything else must be a tracked repository path.
    """
    paths = set()
    for entry in entries:
        for route in entry["existing_routes"]:
            if route["source"].startswith("upstream:"):
                continue
            paths.add(route["source"].split(":", 1)[0])
        paths.update(entry["docs"])
    return sorted(paths)


def build(report, entries):
    status_only = set(report["gaps"]["status_only_components"])
    mapped = {e["component"] for e in entries}
    if mapped != status_only:
        raise MapError("status-only map is stale: unmapped "
                       f"{sorted(status_only - mapped)}, no longer status-only "
                       f"{sorted(mapped - status_only)}")
    rows = []
    for entry in entries:
        name = entry["component"]
        comp = report["components"][name]
        gap = {"status_is_function": "none",
               "missing_wrapper": "missing_tool"}.get(entry["kind"], entry["kind"])
        flags = comp.get("driver_flags", {})
        # Separate fact: an absent driver on this boot is not a missing tool,
        # and does not prove a driver ever worked.
        loaded = (None if not flags else all(flags.values()))
        rows.append(dict(entry, gap=gap, phone_state=comp["phone_state"],
                         driver_flags=flags, driver_loaded_this_boot=loaded,
                         attended=comp["attended"],
                         current_tools=comp["status_tools"]))
    counts = {}
    for row in rows:
        counts[row["gap"]] = counts.get(row["gap"], 0) + 1
    return {"schema_version": 1, "snapshot": report["snapshot"],
            "gap_counts": dict(sorted(counts.items())),
            "note": ("gap comes from the curated map: missing_tool, trial_needed, "
                     "blocked, or none. driver_loaded_this_boot=false only means the "
                     "driver is absent on this boot; it is neither a missing tool nor "
                     "proof a driver ever worked. Attended entries never change "
                     "phone_state."),
            "components": rows}


def text_report(result):
    lines = [f"Status-only components: {len(result['components'])}; snapshot "
             f"{result['snapshot'] or 'none (source-only)'}; gaps {result['gap_counts']}"]
    for row in result["components"]:
        driver = {True: "; driver loaded", False: "; driver NOT loaded this boot",
                  None: ""}[row["driver_loaded_this_boot"]]
        lines.append(f"{row['priority']:>2}. {row['component']} [{row['gap']}] "
                     f"phone={row['phone_state']}{driver}; owner: {row['owner']}")
        if row["gap"] != "none":
            lines.append(f"    missing: {row['missing_tool']}")
            lines.append(f"    proof absent: {row['physical_proof_absent']}")
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--map", default=str(MAP_PATH))
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--status", metavar="FILE")
    group.add_argument("--no-status", action="store_true")
    parser.add_argument("--text", action="store_true")
    args = parser.parse_args(argv)
    try:
        entries = load_map(args.map)
        snapshot = None
        if not args.no_status:
            path = Path(args.status) if args.status else cov.DEFAULT_STATUS
            if args.status or path.exists():
                snapshot = mm.load_snapshot(path)
        result = build(cov.audit(mm.build(), snapshot), entries)
    except (MapError, mm.ManifestError, OSError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1
    if args.text:
        sys.stdout.write(text_report(result))
    else:
        print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
