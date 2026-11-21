#!/usr/bin/env python3
"""Read-only, validation-aware manifest of Lynx's local agent tools.

Builds one JSON document from the source manifests in ``lynx/tools/local_calls``
(``<tool>.json`` plus its ``<tool>.sh`` wrapper). Each tool gets its effect
(read-only, samples the microphone,
actuates, stops, runs a task), the status component it reports on
or depends on, and a source hash so a UI can detect drift from the installed
catalog.

With a snapshot that includes the installed catalog's file hashes, each tool
also gets ``installed``: ``current``, ``differs``, ``missing`` or ``unknown``.

Validation is never inferred from the manifests. Without ``--status`` every
tool's live state is ``unknown``. With ``--status FILE`` the manifest joins a
saved status snapshot (the JSON printed by ``lynx-platform-status all``,
``lynx-peripheral-status all`` and ``lynx-hardware status all``) and reports,
per tool, one of:

- ``validated``       the status source says the function is proven;
- ``interface_only``  kernel interface present, function not proven;
- ``not_ready``       interface absent or unhealthy;
- ``unknown``         no snapshot, or the snapshot lacks this component;
- ``malformed``       the snapshot entry lacks boolean readiness fields.

This program never contacts Lynx, opens sockets, or writes files other than
the ``--write`` output path. A live broker is a separate, reviewed step.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import sys

SCHEMA_VERSION = 1
MAX_SNAPSHOT_BYTES = 1 << 20
NOOBIA = Path(os.environ.get("NOOBIA", "/noobia"))
SOURCE_DIR = NOOBIA / "lynx/tools/local_calls"
MANIFEST_PATH = NOOBIA / "lynx/tools/ui/lynx-tool-manifest.json"
ATTENDED_PATH = NOOBIA / "lynx/tools/ui/attended_evidence.json"

# Status sources and the components each reports, mirroring
# lynx_platform_status.COMPONENTS, lynx_peripheral_status.COMPONENTS and
# lynx_hardware.DEVICES (the offline test keeps these in step).
SOURCES = {
    "platform": ("lynx-platform-status",
                 ("battery", "thermal", "storage", "wifi", "display", "touch",
                  "audio", "haptic", "sensorhub", "usb", "cellular", "sim")),
    "peripheral": ("lynx-peripheral-status", ("nfc", "fingerprint", "headset")),
    "hardware": ("lynx-hardware",
                 ("microphone", "flashlight", "gnss", "bluetooth", "camera")),
}
COMMAND_SOURCE = {command: source for source, (command, _) in SOURCES.items()}

# Every tool must be classified here by hand: an unclassified new tool is an
# error, never silently presented as read-only.
#   effect: read_only | samples_microphone | actuates | stops | runs_task
#   group:  UI section
#   component: (source, component) the tool reports on or depends on, or None
#   reports: True if the tool's own output is that component's status
TOOLS = {
    "lynx_agent_health": ("read_only", "agent", None, False),
    "lynx_queue_health": ("read_only", "agent", None, False),
    "lynx_codex": ("runs_task", "agent", None, False),
    "lynx_platform_status": ("read_only", "overview", ("platform", "*"), True),
    "lynx_peripheral_status": ("read_only", "overview", ("peripheral", "*"), True),
    "lynx_battery_status": ("read_only", "power", ("platform", "battery"), True),
    "lynx_thermal_status": ("read_only", "power", ("platform", "thermal"), True),
    "lynx_storage_status": ("read_only", "system", ("platform", "storage"), True),
    "lynx_wifi_status": ("read_only", "radio", ("platform", "wifi"), True),
    "lynx_bluetooth": ("read_only", "radio", ("hardware", "bluetooth"), True),
    "lynx_gnss": ("read_only", "radio", ("hardware", "gnss"), True),
    "lynx_cellular_status": ("read_only", "radio", ("platform", "cellular"), True),
    "lynx_sim_status": ("read_only", "radio", ("platform", "sim"), True),
    "lynx_nfc_status": ("read_only", "radio", ("peripheral", "nfc"), True),
    "lynx_usb_status": ("read_only", "system", ("platform", "usb"), True),
    "lynx_display_status": ("read_only", "display", ("platform", "display"), True),
    "lynx_touch_status": ("read_only", "display", ("platform", "touch"), True),
    "lynx_touch_events": ("read_only", "display", ("platform", "touch"), False),
    "lynx_fingerprint_status": ("read_only", "display", ("peripheral", "fingerprint"), True),
    "lynx_camera": ("read_only", "camera", ("hardware", "camera"), True),
    "lynx_flashlight": ("read_only", "light", ("hardware", "flashlight"), True),
    "lynx_flashlight_pulse": ("actuates", "light", ("hardware", "flashlight"), False),
    "lynx_flashlight_stop": ("stops", "light", ("hardware", "flashlight"), False),
    "lynx_haptic_status": ("read_only", "haptic", ("platform", "haptic"), True),
    "lynx_haptic_pulse": ("actuates", "haptic", ("platform", "haptic"), False),
    "lynx_haptic_stop": ("stops", "haptic", ("platform", "haptic"), False),
    "lynx_audio_status": ("read_only", "sound", ("platform", "audio"), True),
    "lynx_headset_status": ("read_only", "sound", ("peripheral", "headset"), True),
    "lynx_microphone": ("read_only", "sound", ("hardware", "microphone"), True),
    "lynx_microphone_level": ("samples_microphone", "sound", ("hardware", "microphone"), False),
    "lynx_media_catalog": ("read_only", "sound", ("platform", "audio"), False),
    "lynx_media_status": ("read_only", "sound", ("platform", "audio"), False),
    "lynx_media_play": ("actuates", "sound", ("platform", "audio"), False),
    "lynx_media_stop": ("stops", "sound", ("platform", "audio"), False),
    "lynx_sensorhub_status": ("read_only", "sensors", ("platform", "sensorhub"), True),
    "lynx_motion_read": ("read_only", "sensors", ("platform", "sensorhub"), False),
    "lynx_magnetometer_read": ("read_only", "sensors", ("platform", "sensorhub"), False),
    "lynx_light_read": ("read_only", "sensors", ("platform", "sensorhub"), False),
    "lynx_proximity_read": ("read_only", "sensors", ("platform", "sensorhub"), False),
}

# Tools that also act on or read a second component. The media tools take
# kind=sound or kind=image; images go to the screen (lynx_agent_media.py:16-30).
# Live state still comes from the primary component only.
ALSO_COMPONENTS = {
    "lynx_media_catalog": ("platform/display",),
    "lynx_media_status": ("platform/display",),
    "lynx_media_play": ("platform/display",),
    "lynx_media_stop": ("platform/display",),
}


class ManifestError(Exception):
    pass


def entry_of(script):
    """Return the installed command and arguments a wrapper script execs."""
    for line in script.splitlines():
        line = line.strip()
        if not line.startswith("exec "):
            continue
        try:
            words = shlex.split(line, posix=True)[1:]
        except ValueError:
            # Multi-line inline programs do not tokenize as one line.
            words = line.split()[1:]
        if len(words) >= 2 and words[0].endswith("python3") and words[1] == "-c":
            return {"command": "inline-python", "args": []}
        if words and words[0].endswith("python3"):
            words = words[1:]
        if not words:
            break
        return {"command": Path(words[0]).name, "args": words[1:]}
    raise ManifestError("wrapper has no exec line")


def source_tools(source_dir=SOURCE_DIR):
    source_dir = Path(source_dir)
    names = sorted(p.stem for p in source_dir.glob("*.json"))
    scripts = sorted(p.stem for p in source_dir.glob("*.sh"))
    if names != scripts:
        missing = sorted(set(names) ^ set(scripts))
        raise ManifestError(f"manifest/script pairs differ: {missing}")
    for name, extra in ALSO_COMPONENTS.items():
        for key in extra:
            source, _, part = key.partition("/")
            if name not in TOOLS or part not in SOURCES.get(source, ("", ()))[1]:
                raise ManifestError(f"bad secondary component {key!r} for {name}")
    unclassified = sorted(set(names) - set(TOOLS))
    if unclassified:
        raise ManifestError(f"unclassified tools: {unclassified}")
    stale = sorted(set(TOOLS) - set(names))
    if stale:
        raise ManifestError(f"classified tools missing from source: {stale}")
    tools = []
    for name in names:
        raw_json = (source_dir / f"{name}.json").read_bytes()
        raw_sh = (source_dir / f"{name}.sh").read_bytes()
        try:
            spec = json.loads(raw_json)
        except ValueError as exc:
            raise ManifestError(f"{name}.json is not JSON: {exc}") from None
        if spec.get("name") != name:
            raise ManifestError(f"{name}.json declares name {spec.get('name')!r}")
        schema = spec.get("inputSchema")
        if not isinstance(schema, dict) or schema.get("type") != "object":
            raise ManifestError(f"{name}.json has no object inputSchema")
        timeout = spec.get("timeout")
        if not isinstance(timeout, (int, float)) or timeout <= 0:
            raise ManifestError(f"{name}.json has no positive timeout")
        entry = entry_of(raw_sh.decode("utf-8"))
        effect, group, component, reports = TOOLS[name]
        if component and reports:
            source, part = component
            expected = SOURCES[source][0]
            wanted = "all" if part == "*" else part
            if entry["command"] != expected or wanted not in entry["args"]:
                raise ManifestError(
                    f"{name} is classified as {source}/{part} status but runs "
                    f"{entry['command']} {' '.join(entry['args'])}")
        properties = schema.get("properties") or {}
        tools.append({
            "name": name,
            "description": spec.get("description", ""),
            "effect": effect,
            "group": group,
            "status_source": component[0] if component else None,
            "component": component[1] if component else None,
            "reports_component_status": reports,
            "also_components": list(ALSO_COMPONENTS.get(name, ())),
            "inputs": sorted(properties),
            "required_inputs": sorted(schema.get("required") or []),
            "timeout_s": timeout,
            "nrp_id": spec.get("nrp_id"),
            "entry": entry,
            "files_sha256": {"json": hashlib.sha256(raw_json).hexdigest(),
                             "sh": hashlib.sha256(raw_sh).hexdigest()},
        })
    return tools


ATTENDED_KEYS = {"id", "component", "tools", "claim", "observer", "date", "boot",
                 "receipts", "does_not_establish"}


def load_attended(path=ATTENDED_PATH):
    """Load human-attended confirmations; each must cite a receipt and limits."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ManifestError(f"attended evidence unreadable: {exc}") from None
    entries = data.get("entries") if isinstance(data, dict) else None
    if not isinstance(entries, list):
        raise ManifestError("attended evidence needs an 'entries' list")
    components = {f"{s}/{c}" for s, (_, parts) in SOURCES.items() for c in parts}
    seen = set()
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != ATTENDED_KEYS:
            raise ManifestError(f"attended entry needs exactly {sorted(ATTENDED_KEYS)}")
        ident = entry["id"]
        if not isinstance(ident, str) or ident in seen:
            raise ManifestError(f"attended entry id missing or repeated: {ident!r}")
        seen.add(ident)
        if entry["component"] not in components:
            raise ManifestError(f"{ident}: unknown component {entry['component']!r}")
        for key in ("claim", "observer", "date"):
            if not isinstance(entry[key], str) or not entry[key].strip():
                raise ManifestError(f"{ident}: {key} must be a non-empty string")
        for key in ("tools", "receipts", "does_not_establish"):
            values = entry[key]
            if (not isinstance(values, list) or not values or
                    not all(isinstance(v, str) and v.strip() for v in values)):
                raise ManifestError(f"{ident}: {key} must list at least one item")
    return entries


def build(source_dir=SOURCE_DIR, attended_path=ATTENDED_PATH):
    tools = source_tools(source_dir)
    attended = load_attended(attended_path)
    by_tool = {}
    known = {tool["name"]: tool for tool in tools}
    for entry in attended:
        for name in entry["tools"]:
            tool = known.get(name)
            if tool is None:
                raise ManifestError(f"{entry['id']}: unknown tool {name!r}")
            if f"{tool['status_source']}/{tool['component']}" != entry["component"]:
                raise ManifestError(f"{entry['id']}: {name} does not belong to "
                                    f"{entry['component']}")
            by_tool.setdefault(name, []).append(entry["id"])
    effects = {}
    for tool in tools:
        effects[tool["effect"]] = effects.get(tool["effect"], 0) + 1
        tool["attended"] = by_tool.get(tool["name"], [])
    return {
        "schema_version": SCHEMA_VERSION,
        "entity": "Lynx",
        "source": "lynx/tools/local_calls",
        "tool_count": len(tools),
        "effects": dict(sorted(effects.items())),
        "status_sources": {name: {"command": cmd, "components": list(parts)}
                           for name, (cmd, parts) in SOURCES.items()},
        "validation_states": ["validated", "interface_only", "not_ready",
                              "unknown", "malformed"],
        "install_states": ["current", "differs", "missing", "unknown"],
        "note": ("Interface inventory is not proof of function. A tool's "
                 "'live' state comes only from a status snapshot. 'attended' "
                 "lists separate human confirmations, which never change "
                 "'live'."),
        "attended_evidence": attended,
        "tools": tools,
    }


def load_snapshot(path):
    path = Path(path)
    if path.stat().st_size > MAX_SNAPSHOT_BYTES:
        raise ManifestError(f"status snapshot exceeds {MAX_SNAPSHOT_BYTES} bytes")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError) as exc:
        raise ManifestError(f"status snapshot is not JSON: {exc}") from None
    if not isinstance(data, dict) or not set(data) & (set(SOURCES) | {"catalog"}):
        raise ManifestError("status snapshot needs a 'platform', 'peripheral', "
                            "'hardware' or 'catalog' object")
    return data


def component_state(entry):
    if not isinstance(entry, dict):
        return "malformed", None
    ready, valid = entry.get("interface_ready"), entry.get("validated")
    if not isinstance(ready, bool) or not isinstance(valid, bool):
        return "malformed", None
    nxt = entry.get("next") if isinstance(entry.get("next"), str) else None
    if valid:
        return "validated", nxt
    return ("interface_only" if ready else "not_ready"), nxt


def apply_snapshot(manifest, snapshot):
    """Return a copy of manifest with per-tool live state from snapshot."""
    result = json.loads(json.dumps(manifest))
    components = {}
    for source, (_, parts) in SOURCES.items():
        section = snapshot.get(source)
        for part in parts:
            if not isinstance(section, dict) or part not in section:
                components[(source, part)] = ("unknown", None)
            else:
                components[(source, part)] = component_state(section[part])
    for tool in result["tools"]:
        source, part = tool["status_source"], tool["component"]
        if source is None:
            tool["live"] = {"state": "unknown",
                            "why": "no status component; call the tool itself"}
        elif part == "*":
            counts = {}
            for (src, _), (state, _) in components.items():
                if src == source:
                    counts[state] = counts.get(state, 0) + 1
            tool["live"] = {"state": "summary", "counts": dict(sorted(counts.items()))}
        else:
            state, nxt = components[(source, part)]
            tool["live"] = {"state": state}
            if nxt:
                tool["live"]["next"] = nxt
    catalog = snapshot.get("catalog")
    files = catalog.get("files") if isinstance(catalog, dict) else None
    if not isinstance(files, dict):
        files = None
    installs = {}
    for tool in result["tools"]:
        if files is None:
            state = "unknown"
        else:
            got = [files.get(f"{tool['name']}.{ext}") for ext in ("json", "sh")]
            want = [tool["files_sha256"][ext] for ext in ("json", "sh")]
            state = ("missing" if None in got else
                     "current" if got == want else "differs")
        tool["installed"] = state
        installs[state] = installs.get(state, 0) + 1
    extra = []
    if files is not None:
        known = {t["name"] for t in result["tools"]}
        extra = sorted({name.rsplit(".", 1)[0] for name in files} - known)
    summary = {}
    for state, _ in components.values():
        summary[state] = summary.get(state, 0) + 1
    result["snapshot"] = {
        "captured_at": snapshot.get("captured_at") if isinstance(
            snapshot.get("captured_at"), str) else None,
        "boot": snapshot.get("boot") if isinstance(snapshot.get("boot"), dict) else None,
        "previous": (snapshot.get("previous")
                     if isinstance(snapshot.get("previous"), dict) else None),
        "component_states": dict(sorted(summary.items())),
        "install_states": dict(sorted(installs.items())),
        "installed_not_in_source": extra,
        "errors": snapshot.get("errors") if isinstance(snapshot.get("errors"), dict) else {},
        "components": {f"{src}/{part}": state
                       for (src, part), (state, _) in sorted(components.items())},
    }
    return result


def render(manifest):
    return json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--source", default=str(SOURCE_DIR),
                        help="directory of <tool>.json and <tool>.sh pairs")
    parser.add_argument("--status", metavar="FILE",
                        help="saved status snapshot JSON to join (never fetched live)")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", metavar="FILE", nargs="?", const=str(MANIFEST_PATH),
                      help="verify a committed manifest matches the sources")
    mode.add_argument("--write", metavar="FILE", nargs="?", const=str(MANIFEST_PATH),
                      help="write the offline manifest (no snapshot) to FILE")
    mode.add_argument("--summary", action="store_true",
                      help="print one line per tool instead of JSON")
    args = parser.parse_args(argv)
    try:
        manifest = build(args.source)
        if args.check:
            if args.status:
                parser.error("--check compares the offline manifest; omit --status")
            try:
                committed = Path(args.check).read_text(encoding="utf-8")
            except OSError as exc:
                raise ManifestError(f"cannot read {args.check}: {exc.strerror}") from None
            if committed != render(manifest):
                print(json.dumps({"ok": False, "error": "manifest is stale; "
                                  "regenerate with --write", "path": args.check}))
                return 1
            print(json.dumps({"ok": True, "tool_count": manifest["tool_count"],
                              "path": args.check}))
            return 0
        if args.write:
            if args.status:
                parser.error("--write stores the offline manifest; omit --status")
            Path(args.write).write_text(render(manifest), encoding="utf-8")
            print(json.dumps({"ok": True, "tool_count": manifest["tool_count"],
                              "path": args.write}))
            return 0
        if args.status:
            manifest = apply_snapshot(manifest, load_snapshot(args.status))
        if args.summary:
            for tool in manifest["tools"]:
                where = (f"{tool['status_source']}/{tool['component']}"
                         if tool["status_source"] else "-")
                live = tool.get("live", {}).get("state", "unknown")
                installed = tool.get("installed", "unknown")
                print(f"{tool['name']}\t{tool['effect']}\t{where}\t{live}\t{installed}")
            return 0
        sys.stdout.write(render(manifest))
        return 0
    except (ManifestError, OSError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
