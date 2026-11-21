#!/usr/bin/env python3
"""Read-only coverage audit of Lynx's agent tools against hardware status.

Joins the tracked 38-tool manifest (``lynx/tools/local_calls``), the attended
evidence file, and an optional saved status snapshot (``state/latest.json``
from ``lynx_status_snapshot.py``). Reports:

- per component: its status, read, action and stop tools, phone-reported
  state, and attended confirmations, kept apart;
- components with no tool at all, and components with only a status tool;
- tools that act (``actuates``, ``runs_task``) without a stop tool and a
  read-only status companion for the same component;
- source-versus-installed catalog drift;
- unverified functions, and for parts that are not ready, why: no tool
  source, tool not installed, driver not loaded, or interface absent.

A driver flag of ``false`` only says the driver is absent on this boot. It does
not prove a driver ever worked. Earlier success is listed separately
(attended entries, or ``*_verified``/``visual_confirmation_recorded`` evidence
flags that are true).

Never contacts Lynx: pass a snapshot captured separately.

  lynx_tool_coverage.py                     # JSON, using state/latest.json if present
  lynx_tool_coverage.py --text              # short human report
  lynx_tool_coverage.py --status FILE       # a specific snapshot
  lynx_tool_coverage.py --no-status         # source-only audit
"""

import argparse
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import lynx_snapshot_age as age_mod  # noqa: E402
import lynx_tool_manifest as mm  # noqa: E402

DEFAULT_STATUS = HERE / "state" / "latest.json"
DRIVER_FLAGS = ("driver_loaded", "driver_bound")
AGENT = "agent/*"  # pseudo-component for tools with no hardware status component
NEEDS_STOP = ("actuates", "runs_task")


def prior_success(evidence):
    """Evidence flags recording an earlier successful trial."""
    if not isinstance(evidence, dict):
        return []
    return sorted(key for key, value in evidence.items()
                  if value is True and (key.endswith("_verified") or
                                        key == "visual_confirmation_recorded"))


def driver_flags(evidence):
    if not isinstance(evidence, dict):
        return {}
    return {key: evidence[key] for key in DRIVER_FLAGS
            if isinstance(evidence.get(key), bool)}


def audit(manifest, snapshot=None, now=None):
    if snapshot is not None:
        manifest = mm.apply_snapshot(manifest, snapshot)
    attended = {e["id"]: e for e in manifest["attended_evidence"]}
    components = {}
    for source, (_, parts) in mm.SOURCES.items():
        for part in parts:
            components[f"{source}/{part}"] = {
                "status_tools": [], "read_tools": [], "action_tools": [],
                "stop_tools": [], "attended": []}
    components[AGENT] = {"status_tools": [], "read_tools": [], "action_tools": [],
                         "stop_tools": [], "attended": []}
    snap_parts = (manifest.get("snapshot") or {}).get("components", {})

    for tool in manifest["tools"]:
        if tool["component"] == "*":
            continue  # aggregate overview tools report every component
        key = (f"{tool['status_source']}/{tool['component']}"
               if tool["status_source"] else AGENT)
        for target in [key] + list(tool.get("also_components", [])):
            entry = components[target]
            primary = target == key
            if tool["effect"] in NEEDS_STOP:
                entry["action_tools"].append(tool["name"])
            elif tool["effect"] == "stops":
                entry["stop_tools"].append(tool["name"])
            elif primary and (tool["reports_component_status"] or key == AGENT):
                entry["status_tools"].append(tool["name"])
            else:
                entry["read_tools"].append(tool["name"])
            if primary:  # attended evidence belongs to the primary component only
                for ident in tool["attended"]:
                    if ident not in entry["attended"]:
                        entry["attended"].append(ident)

    no_tool, status_only, unverified, unknown, not_ready = [], [], [], [], []
    for key, entry in components.items():
        tools = (entry["status_tools"] + entry["read_tools"] +
                 entry["action_tools"] + entry["stop_tools"])
        if key == AGENT:
            entry["phone_state"] = None
            continue
        source, part = key.split("/", 1)
        raw = (snapshot or {}).get(source, {})
        raw = raw.get(part) if isinstance(raw, dict) else None
        evidence = raw.get("evidence") if isinstance(raw, dict) else None
        state = snap_parts.get(key, "unknown")
        entry["phone_state"] = state
        entry["driver_flags"] = driver_flags(evidence)
        entry["prior_success_flags"] = prior_success(evidence)
        if not tools:
            no_tool.append(key)
        elif not (entry["read_tools"] or entry["action_tools"]):
            status_only.append(key)
        if state in ("unknown", "malformed"):
            unknown.append(key)
        elif state != "validated":
            unverified.append({"component": key, "phone_state": state,
                               "prior_success_flags": entry["prior_success_flags"],
                               "attended": entry["attended"]})
        if state == "not_ready":
            installed = {t["name"]: t.get("installed", "unknown")
                         for t in manifest["tools"] if t["name"] in tools}
            if not tools:
                cause = "no_tool_source"
            elif any(v == "missing" for v in installed.values()):
                cause = "tool_not_installed"
            elif any(v is False for v in entry["driver_flags"].values()):
                cause = "driver_not_loaded"
            else:
                cause = "interface_absent"
            not_ready.append({
                "component": key, "cause": cause,
                "driver_flags": entry["driver_flags"],
                "prior_success_flags": entry["prior_success_flags"],
                "attended": entry["attended"],
                "next": raw.get("next") if isinstance(raw, dict) else None})

    companions = []
    for key, entry in components.items():
        readers = entry["status_tools"] + entry["read_tools"]
        for name in entry["action_tools"]:
            missing = []
            if not entry["stop_tools"]:
                missing.append("stop")
            if not readers:
                missing.append("status")
            companions.append({"tool": name, "component": key,
                               "stop_tools": entry["stop_tools"],
                               "status_tools": readers, "missing": missing})

    snap = manifest.get("snapshot")
    if snap is None:
        drift = {"checked": False}
    else:
        tools = manifest["tools"]
        drift = {"checked": "catalog" in (snapshot or {}),
                 "differs": [t["name"] for t in tools if t.get("installed") == "differs"],
                 "missing": [t["name"] for t in tools if t.get("installed") == "missing"],
                 "installed_not_in_source": snap["installed_not_in_source"]}

    return {
        "schema_version": 1,
        "tool_count": manifest["tool_count"],
        "snapshot": (snap or {}).get("captured_at") if snap else None,
        "snapshot_errors": (snap or {}).get("errors", {}) if snap else {},
        "snapshot_freshness": age_mod.freshness(snapshot, now) if snapshot is not None else None,
        "note": ("phone_state comes only from Lynx's status code; 'attended' "
                 "lists separate human confirmations and never changes it. A "
                 "false driver flag means absent on this boot, not that a "
                 "driver once worked."),
        "components": components,
        "gaps": {
            "components_without_tools": no_tool,
            "status_only_components": status_only,
            "actions_missing_companions": [c for c in companions if c["missing"]],
            "catalog_drift": drift,
            "unverified": unverified,
            "phone_state_unknown": unknown,
            "not_ready": not_ready,
        },
        "action_companions": companions,
    }


def text_report(report):
    gaps = report["gaps"]
    lines = [f"Lynx tool coverage: {report['tool_count']} tools; snapshot "
             f"{report['snapshot'] or 'none (source-only)'}"]
    fresh = report["snapshot_freshness"]
    if fresh:
        lines.append(f"snapshot freshness: {fresh['state']}; boot "
                     f"{fresh['boot_id'] or 'unknown'} ({fresh['boot_state']}); {fresh['summary']}")
        if not fresh["current"]:
            lines.append("WARNING: states below are as captured, not current")
    if report["snapshot_errors"]:
        lines.append("snapshot errors: " + "; ".join(
            f"{k}: {v}" for k, v in sorted(report["snapshot_errors"].items())))
    lines.append("components without tools: " +
                 (", ".join(gaps["components_without_tools"]) or "none"))
    lines.append("status-only components (no separate read or action tool): " +
                 (", ".join(gaps["status_only_components"]) or "none"))
    for item in report["action_companions"]:
        verdict = ("missing " + " and ".join(item["missing"])) if item["missing"] else "ok"
        lines.append(f"action {item['tool']} ({item['component']}): {verdict}; "
                     f"stop={','.join(item['stop_tools']) or '-'} "
                     f"status={','.join(item['status_tools']) or '-'}")
    drift = gaps["catalog_drift"]
    if not drift.get("checked"):
        lines.append("catalog drift: not checked (no catalog in snapshot)")
    else:
        lines.append(f"catalog drift: differs={drift['differs'] or 'none'} "
                     f"missing={drift['missing'] or 'none'} "
                     f"extra={drift['installed_not_in_source'] or 'none'}")
    for item in gaps["not_ready"]:
        flags = ",".join(f"{k}={str(v).lower()}" for k, v in item["driver_flags"].items())
        prior = ",".join(item["prior_success_flags"] + item["attended"]) or "none"
        lines.append(f"not ready {item['component']}: {item['cause']}"
                     + (f" ({flags})" if flags else "") + f"; prior success: {prior}")
    unverified = [u for u in gaps["unverified"] if u["phone_state"] != "not_ready"]
    for item in unverified:
        attended = ", ".join(item["attended"]) or "none"
        prior = ",".join(item["prior_success_flags"]) or "none"
        lines.append(f"unverified {item['component']}: phone {item['phone_state']}; "
                     f"prior success flags: {prior}; attended (separate): {attended}")
    if gaps["phone_state_unknown"]:
        lines.append(f"phone state unknown ({len(gaps['phone_state_unknown'])}): "
                     + ", ".join(gaps["phone_state_unknown"]))
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--source", default=str(mm.SOURCE_DIR))
    parser.add_argument("--attended", default=str(mm.ATTENDED_PATH))
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--status", metavar="FILE")
    group.add_argument("--no-status", action="store_true")
    parser.add_argument("--text", action="store_true", help="short human report")
    parser.add_argument("--now", metavar="UTC", help="evaluate age at this time "
                        "(YYYY-MM-DDTHH:MM:SSZ), for reproducible output")
    args = parser.parse_args(argv)
    try:
        manifest = mm.build(args.source, args.attended)
        snapshot = None
        if not args.no_status:
            path = Path(args.status) if args.status else DEFAULT_STATUS
            if args.status or path.exists():
                snapshot = mm.load_snapshot(path)
        now = None
        if args.now:
            now = age_mod.parse_time(args.now)
            if now is None:
                raise mm.ManifestError("--now must be YYYY-MM-DDTHH:MM:SSZ")
        report = audit(manifest, snapshot, now)
    except (mm.ManifestError, OSError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1
    if args.text:
        sys.stdout.write(text_report(report))
    else:
        print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
