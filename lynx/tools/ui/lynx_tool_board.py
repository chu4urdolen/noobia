#!/usr/bin/env python3
"""Render Lynx's tool board: a read-only HTML page of tools and live status.

Joins the tool manifest with a saved status snapshot and writes one
self-contained HTML file (no scripts, no network, no buttons that act). It
shows what each tool does, whether its hardware function is proven or only
present, and whether the installed copy matches source.

  lynx_tool_board.py                    # render state/board.html from state/latest.json
  lynx_tool_board.py --refresh          # capture a new snapshot first (read-only SSH)
  lynx_tool_board.py --status FILE --out FILE
"""

import argparse
from datetime import datetime, timezone
import html
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import lynx_tool_manifest as manifest_mod  # noqa: E402

STATE_DIR = HERE / "state"
DEFAULT_STATUS = STATE_DIR / "latest.json"
DEFAULT_OUT = STATE_DIR / "board.html"

GROUPS = [
    ("overview", "Overview"), ("power", "Power"), ("system", "System"),
    ("radio", "Radios"), ("display", "Screen and touch"), ("camera", "Camera"),
    ("light", "Flashlight"), ("haptic", "Haptics"), ("sound", "Sound"),
    ("sensors", "Sensors"), ("agent", "Local agent"),
]
STATE_LABEL = {
    "validated": "proven", "interface_only": "present, unproven",
    "not_ready": "not ready", "unknown": "unknown", "malformed": "bad reading",
    "summary": "summary",
}
EFFECT_LABEL = {
    "read_only": "reads", "samples_microphone": "samples mic",
    "actuates": "acts", "stops": "stops", "runs_task": "runs task",
}
INSTALL_LABEL = {
    "current": "installed", "differs": "installed copy differs",
    "missing": "not installed", "unknown": "install unknown",
}

CSS = """
:root{--bg:#f6f5f2;--card:#fff;--ink:#1d2024;--muted:#5d646d;--line:#dcdad4;
--ok:#1f7a4d;--ok-bg:#e3f3ea;--warn:#8a5a00;--warn-bg:#fbf0d9;--bad:#a2312b;
--bad-bg:#f9e3e1;--na:#555c66;--na-bg:#eceef1;--act:#6b3fa0;--act-bg:#efe7f8}
@media (prefers-color-scheme:dark){:root{--bg:#15171a;--card:#1e2125;--ink:#e8e6e1;
--muted:#9aa1aa;--line:#33373d;--ok:#6fd3a0;--ok-bg:#183326;--warn:#f0c46a;
--warn-bg:#3a2e14;--bad:#f39a92;--bad-bg:#3d1f1c;--na:#aab1ba;--na-bg:#2a2e33;
--act:#c9a8f0;--act-bg:#2e2340}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
font:15px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1100px;margin:0 auto;padding:24px 16px 48px}
h1{font-size:26px;margin:0 0 4px}h2{font-size:17px;margin:28px 0 10px}
.sub{color:var(--muted);margin:0 0 16px}
.warn-box{border:1px solid var(--bad);background:var(--bad-bg);color:var(--bad);
padding:10px 12px;border-radius:8px;margin:12px 0}
.chips{display:flex;flex-wrap:wrap;gap:6px}
.chip,.badge{display:inline-block;border-radius:999px;padding:2px 10px;font-size:13px;
white-space:nowrap}
.s-validated{background:var(--ok-bg);color:var(--ok)}
.s-interface_only{background:var(--warn-bg);color:var(--warn)}
.s-not_ready,.s-malformed,.i-differs,.i-missing{background:var(--bad-bg);color:var(--bad)}
.s-unknown,.s-summary,.i-unknown,.e-read_only{background:var(--na-bg);color:var(--na)}
.i-current{background:var(--ok-bg);color:var(--ok)}
.e-actuates,.e-stops,.e-runs_task,.e-samples_microphone{background:var(--act-bg);color:var(--act)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(310px,1fr));gap:10px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px}
.card h3{font:600 14px ui-monospace,SFMono-Regular,Menlo,monospace;margin:0 0 6px;
overflow-wrap:anywhere}
.badges{display:flex;flex-wrap:wrap;gap:4px;margin-bottom:6px}
.card p{margin:4px 0;font-size:13.5px}.next{color:var(--muted)}
.meta{color:var(--muted);font-size:12px}
.legend{font-size:13px;color:var(--muted)}
footer{margin-top:32px;color:var(--muted);font-size:13px}
"""


def esc(value):
    return html.escape(str(value), quote=True)


def age_text(captured_at, now):
    try:
        then = datetime.strptime(captured_at, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return "unknown age"
    seconds = int((now - then).total_seconds())
    if seconds < 0:
        return "from the future (check clocks)"
    if seconds < 120:
        return f"{seconds} s old"
    if seconds < 7200:
        return f"{seconds // 60} min old"
    return f"{seconds // 3600} h old"


def card(tool):
    live = tool.get("live", {"state": "unknown"})
    state = live["state"]
    installed = tool.get("installed", "unknown")
    where = (f"{tool['status_source']}/{tool['component']}"
             if tool["status_source"] and tool["component"] != "*" else None)
    badges = [
        f'<span class="badge e-{esc(tool["effect"])}">{esc(EFFECT_LABEL[tool["effect"]])}</span>',
        f'<span class="badge s-{esc(state)}">{esc(STATE_LABEL.get(state, state))}</span>',
        f'<span class="badge i-{esc(installed)}">{esc(INSTALL_LABEL.get(installed, installed))}</span>',
    ]
    desc = tool["description"].removeprefix("Entity: Lynx. ")
    parts = [f'<div class="card" data-tool="{esc(tool["name"])}">',
             f'<h3>{esc(tool["name"])}</h3>',
             f'<div class="badges">{"".join(badges)}</div>',
             f"<p>{esc(desc)}</p>"]
    if live.get("next"):
        parts.append(f'<p class="next">Next: {esc(live["next"])}</p>')
    if state == "summary":
        counts = ", ".join(f"{n} {STATE_LABEL.get(s, s)}"
                           for s, n in live.get("counts", {}).items())
        parts.append(f'<p class="next">{esc(counts)}</p>')
    meta = [f"timeout {tool['timeout_s']} s"]
    if tool["inputs"]:
        meta.append("inputs: " + ", ".join(tool["inputs"]))
    if where:
        meta.append(f"status: {where}")
    parts.append(f'<p class="meta">{esc(" · ".join(meta))}</p></div>')
    return "".join(parts)


def render(manifest, now=None):
    now = now or datetime.now(timezone.utc)
    snap = manifest.get("snapshot")
    out = ["<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">",
           "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">",
           "<title>Lynx Tool Board</title>", f"<style>{CSS}</style></head><body><main>",
           "<h1>Lynx tool board</h1>"]
    if snap:
        out.append(f'<p class="sub">Snapshot {esc(snap["captured_at"] or "time unknown")} '
                   f'({esc(age_text(snap["captured_at"], now))}) · '
                   f'{manifest["tool_count"]} tools · read-only view</p>')
        if snap.get("errors"):
            items = "; ".join(f"{k}: {v}" for k, v in sorted(snap["errors"].items()))
            out.append(f'<div class="warn-box">Some sources failed, so their tools '
                       f'show unknown. {esc(items)}</div>')
        drift = {k: v for k, v in snap.get("install_states", {}).items() if k != "current"}
        if drift.get("differs") or drift.get("missing") or snap.get("installed_not_in_source"):
            extra = ", ".join(snap.get("installed_not_in_source") or [])
            out.append('<div class="warn-box">Installed catalog differs from source: '
                       f'{esc(json.dumps(drift))}'
                       + (f"; installed only on phone: {esc(extra)}" if extra else "")
                       + "</div>")
        out.append("<h2>Hardware components</h2><div class=\"chips\">")
        for name, state in snap["components"].items():
            out.append(f'<span class="chip s-{esc(state)}">{esc(name.split("/", 1)[1])}: '
                       f'{esc(STATE_LABEL.get(state, state))}</span>')
        out.append("</div>")
    else:
        out.append('<p class="sub">No status snapshot: every live state is unknown.</p>')
    out.append('<p class="legend">“Proven” comes only from Lynx\'s own status code. '
               '“Present, unproven” means the kernel interface exists but no tested '
               'function backs it. Human-attended trials recorded in forge notes are '
               'not reflected here.</p>')
    by_group = {}
    for tool in manifest["tools"]:
        by_group.setdefault(tool["group"], []).append(tool)
    for key, title in GROUPS:
        tools = by_group.pop(key, [])
        if tools:
            out.append(f"<h2>{esc(title)}</h2><div class=\"grid\">")
            out.extend(card(tool) for tool in tools)
            out.append("</div>")
    for key, tools in sorted(by_group.items()):
        out.append(f"<h2>{esc(key)}</h2><div class=\"grid\">")
        out.extend(card(tool) for tool in tools)
        out.append("</div>")
    out.append(f"<footer>Rendered {esc(now.strftime('%Y-%m-%d %H:%M:%S UTC'))} by "
               "lynx/tools/ui/lynx_tool_board.py. This page cannot act on Lynx.</footer>")
    out.append("</main></body></html>\n")
    return "".join(out)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--status", default=str(DEFAULT_STATUS))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--source", default=str(manifest_mod.SOURCE_DIR))
    parser.add_argument("--refresh", action="store_true",
                        help="capture a fresh read-only snapshot before rendering")
    args = parser.parse_args(argv)
    capture_result = None
    if args.refresh:
        import lynx_status_snapshot as snapshot_mod
        snapshot = snapshot_mod.capture()
        captured = [n for n in snapshot_mod.COMMANDS if n in snapshot]
        if captured:
            snapshot_mod.write_atomic(args.status, snapshot)
        capture_result = {"captured": captured, "errors": snapshot["errors"]}
    try:
        manifest = manifest_mod.build(args.source)
        status_path = Path(args.status)
        if status_path.exists():
            manifest = manifest_mod.apply_snapshot(
                manifest, manifest_mod.load_snapshot(status_path))
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(render(manifest), encoding="utf-8")
    except (manifest_mod.ManifestError, OSError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1
    snap = manifest.get("snapshot") or {}
    result = {"ok": True, "path": str(out), "tool_count": manifest["tool_count"],
              "snapshot": snap.get("captured_at"),
              "component_states": snap.get("component_states", {}),
              "install_states": snap.get("install_states", {})}
    if capture_result is not None:
        result["capture"] = capture_result
        result["ok"] = not capture_result["errors"]
    print(json.dumps(result, sort_keys=True))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    sys.exit(main())
