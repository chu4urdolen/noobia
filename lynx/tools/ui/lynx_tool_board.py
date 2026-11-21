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
import os
from pathlib import Path
import sys
import tempfile

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import lynx_health_view as health_mod  # noqa: E402
import lynx_snapshot_age as age_mod  # noqa: E402
import lynx_tool_manifest as manifest_mod  # noqa: E402

STATE_DIR = HERE / "state"
DEFAULT_STATUS = STATE_DIR / "latest.json"
DEFAULT_OUT = STATE_DIR / "board.html"
DEFAULT_HEALTH = STATE_DIR / "health.json"

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
:root{--bg:#f6f5f2;--card:#fff;--ink:#1d2024;--muted:#525960;--line:#dcdad4;
--ok:#14603b;--ok-bg:#e3f3ea;--warn:#8a5a00;--warn-bg:#fbf0d9;--bad:#a2312b;
--bad-bg:#f9e3e1;--na:#555c66;--na-bg:#eceef1;--act:#6b3fa0;--act-bg:#efe7f8;--hum:#1f5f99;--hum-bg:#e2eefa}
@media (prefers-color-scheme:dark){:root{--bg:#15171a;--card:#1e2125;--ink:#e8e6e1;
--muted:#9aa1aa;--line:#33373d;--ok:#6fd3a0;--ok-bg:#183326;--warn:#f0c46a;
--warn-bg:#3a2e14;--bad:#f39a92;--bad-bg:#3d1f1c;--na:#aab1ba;--na-bg:#2a2e33;
--act:#c9a8f0;--act-bg:#2e2340;--hum:#8cc4f5;--hum-bg:#1a2c3e}}
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
.h-attended{background:var(--hum-bg);color:var(--hum)}
.attended{border-left:3px solid var(--hum);padding-left:8px}
.evidence{background:var(--card);border:1px solid var(--line);border-radius:10px;
padding:12px;margin-bottom:8px}.evidence p{margin:4px 0;font-size:13.5px}
footer{max-width:1100px;margin:0 auto;padding:0 16px 32px;color:var(--muted);font-size:13px}
.sr{position:absolute;width:1px;height:1px;margin:-1px;overflow:hidden;
clip:rect(0 0 0 0);white-space:nowrap;border:0}
ul.chips,ul.grid,ul.evidence-list,nav ul{list-style:none;margin:0;padding:0}
nav ul{display:flex;flex-wrap:wrap;gap:6px 14px;font-size:14px}
a{color:var(--hum);text-underline-offset:2px}
a:focus-visible{outline:3px solid var(--ink);outline-offset:2px;border-radius:3px}
.asof{font-style:italic}
"""


def write_text_atomic(path, text):
    """Write a file so readers see either the old or the new page, never half."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".board-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def esc(value):
    return html.escape(str(value), quote=True)


def card(tool, attended=None, current=True):
    live = tool.get("live", {"state": "unknown"})
    state = live["state"]
    installed = tool.get("installed", "unknown")
    where = (f"{tool['status_source']}/{tool['component']}"
             if tool["status_source"] and tool["component"] != "*" else None)
    asof = ("" if current or state in ("unknown", "summary")
            else ' <span class="asof">(as captured)</span>')
    badges = [
        f'<span class="badge e-{esc(tool["effect"])}"><span class="sr">Effect: </span>'
        f'{esc(EFFECT_LABEL[tool["effect"]])}</span>',
        f'<span class="badge s-{esc(state)}"><span class="sr">Phone state: </span>'
        f'{esc(STATE_LABEL.get(state, state))}{asof}</span>',
        f'<span class="badge i-{esc(installed)}"><span class="sr">Install: </span>'
        f'{esc(INSTALL_LABEL.get(installed, installed))}</span>',
    ]
    if tool.get("attended"):
        badges.append('<span class="badge h-attended"><span class="sr">Human check: </span>'
                      'attended</span>')
    desc = tool["description"].removeprefix("Entity: Lynx. ")
    parts = [f'<li class="card" data-tool="{esc(tool["name"])}">',
             f'<h3>{esc(tool["name"])}</h3>',
             f'<div class="badges">{"".join(badges)}</div>',
             f"<p>{esc(desc)}</p>"]
    if live.get("next"):
        parts.append(f'<p class="next">Next: {esc(live["next"])}</p>')
    if state == "summary":
        counts = ", ".join(f"{n} {STATE_LABEL.get(s, s)}"
                           for s, n in live.get("counts", {}).items())
        parts.append(f'<p class="next">{esc(counts)}</p>')
    for ident in tool.get("attended", []):
        entry = (attended or {}).get(ident)
        if entry:
            parts.append(f'<p class="attended">Attended {esc(entry["date"])} '
                         f'({esc(entry["observer"])}): {esc(entry["claim"])}</p>')
    meta = [f"timeout {tool['timeout_s']} s"]
    if tool["inputs"]:
        meta.append("inputs: " + ", ".join(tool["inputs"]))
    if where:
        meta.append(f"status: {where}")
    parts.append(f'<p class="meta">{esc(" · ".join(meta))}</p></li>')
    return "".join(parts)


def render(manifest, now=None, health=None, health_error=None):
    now = now or datetime.now(timezone.utc)
    snap = manifest.get("snapshot")
    out = ["<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">",
           "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">",
           "<title>Lynx Tool Board</title>", f"<style>{CSS}{health_mod.CSS}</style></head><body><main>",
           "<header><h1>Lynx tool board</h1>"]
    fresh = age_mod.freshness(snap, now) if snap else None
    if snap:
        boot = fresh["boot_id"] or "unknown"
        out.append(f'<p class="sub" data-freshness="{esc(fresh["state"])}" '
                   f'data-boot="{esc(fresh["boot_state"])}">'
                   f'Snapshot {esc(snap["captured_at"] or "time unknown")} · '
                   f'{esc(age_mod.age_text(fresh["age_s"]) if fresh["state"] == "fresh" else fresh["state"].replace("_", " "))} · '
                   f'boot {esc(boot)} · {manifest["tool_count"]} tools · read-only view</p>')
        if not fresh["current"] or fresh["boot_state"] == "changed_since_previous":
            out.append(f'<div class="warn-box stale-box" role="status"><strong>'
                       f'{esc(fresh["summary"])}.</strong> Every state below is what Lynx '
                       'reported at capture time, not now. Refresh with '
                       'lynx_tool_board.py --refresh.</div>')
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
    else:
        out.append('<p class="sub">No status snapshot: every live state is unknown.</p>')
    out.append("</header>")
    attended = {e["id"]: e for e in manifest.get("attended_evidence", [])}
    by_group = {}
    for tool in manifest["tools"]:
        by_group.setdefault(tool["group"], []).append(tool)
    sections = [(key, title, by_group.pop(key)) for key, title in GROUPS if key in by_group]
    sections += [(key, key, tools) for key, tools in sorted(by_group.items())]
    links = ([("components", "Hardware components")] if snap else [])
    links += [("health", "Health")] if (health or health_error) else []
    links += [(f"g-{key}", title) for key, title, _ in sections]
    links += [("attended", "Attended confirmations")] if attended else []
    out.append('<nav aria-label="Sections"><ul>' + "".join(
        f'<li><a href="#{esc(ident)}">{esc(title)}</a></li>' for ident, title in links)
        + "</ul></nav>")
    current = bool(fresh and fresh["current"])
    if snap:
        heading = ("Hardware components" if current
                   else "Hardware components (as captured, not current)")
        out.append(f'<section aria-labelledby="components"><h2 id="components">{esc(heading)}</h2>'
                   '<ul class="chips" aria-label="Phone-reported component states">')
        for name, state in snap["components"].items():
            out.append(f'<li class="chip s-{esc(state)}">{esc(name.split("/", 1)[1])}: '
                       f'{esc(STATE_LABEL.get(state, state))}</li>')
        out.append("</ul></section>")
    out.append('<p class="legend">The component chips and each card\'s first state '
               'badge come only from Lynx\'s own status code. “Present, unproven” '
               'means the kernel interface exists but the phone\'s code does not '
               'claim a tested function. A blue “attended” badge is separate: a '
               'person confirmed one specific function once, with a receipt. It '
               'does not change the phone-reported state and may not hold on '
               'the current boot.</p>')
    if health or health_error:
        out.append(health_mod.section(health, now, health_error))
    for key, title, tools in sections:
        count = f"{len(tools)} tool" + ("s" if len(tools) != 1 else "")
        out.append(f'<section aria-labelledby="g-{esc(key)}"><h2 id="g-{esc(key)}">{esc(title)}'
                   f' <span class="sr">({count})</span></h2><ul class="grid">')
        out.extend(card(tool, attended, current) for tool in tools)
        out.append("</ul></section>")
    if attended:
        out.append('<section aria-labelledby="attended"><h2 id="attended">Attended confirmations</h2>'
                   '<p class="legend">Human observations of one function each, '
                   'kept apart from phone-reported validation.</p><ul class="evidence-list">')
        for entry in attended.values():
            component = entry["component"].split("/", 1)[1]
            boot = f" · boot {entry['boot']}" if entry.get("boot") else ""
            relation = age_mod.attended_boot(entry.get("boot"),
                                             fresh["boot_id"] if fresh else None)
            relation_text = {
                "same_boot": "Same boot as this snapshot; still history, not a live check.",
                "earlier_boot": "Earlier boot than this snapshot; may not hold now.",
                "boot_not_recorded": "Boot not recorded; may not hold now.",
                "snapshot_boot_unknown": "Snapshot boot unknown; may not hold now.",
            }[relation]
            out.append('<li class="evidence">'
                       f'<p><span class="badge h-attended">{esc(component)}</span> '
                       f'{esc(entry["date"])} · {esc(entry["observer"])}{esc(boot)}</p>'
                       f'<p>{esc(entry["claim"])}</p>'
                       f'<p class="next">Does not establish: '
                       f'{esc("; ".join(entry["does_not_establish"]))}</p>'
                       f'<p class="meta">Receipts: {esc("; ".join(entry["receipts"]))}</p>'
                       f'<p class="meta" data-boot-relation="{esc(relation)}">'
                       f'{esc(relation_text)}</p>'
                       "</li>")
        out.append("</ul></section>")
    out.append("</main>")
    out.append(f"<footer>Rendered {esc(now.strftime('%Y-%m-%d %H:%M:%S UTC'))} by "
               "lynx/tools/ui/lynx_tool_board.py. This page cannot act on Lynx.</footer>")
    out.append("</body></html>\n")
    return "".join(out)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--status", default=str(DEFAULT_STATUS))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--source", default=str(manifest_mod.SOURCE_DIR))
    parser.add_argument("--health", metavar="FILE",
                        help="saved portable-health/1 report (default: state/health.json "
                             "if present); never collected by this command")
    parser.add_argument("--refresh", action="store_true",
                        help="capture a fresh read-only snapshot before rendering")
    args = parser.parse_args(argv)
    capture_result = None
    if args.refresh:
        import lynx_status_snapshot as snapshot_mod
        snapshot = snapshot_mod.capture()
        captured = [n for n in snapshot_mod.COMMANDS if n in snapshot]
        if captured:
            snapshot = snapshot_mod.with_previous(snapshot, args.status)
            snapshot_mod.write_atomic(args.status, snapshot)
        capture_result = {"captured": captured, "errors": snapshot["errors"]}
    try:
        manifest = manifest_mod.build(args.source)
        status_path = Path(args.status)
        if status_path.exists():
            manifest = manifest_mod.apply_snapshot(
                manifest, manifest_mod.load_snapshot(status_path))
        health = health_error = None
        health_path = Path(args.health) if args.health else DEFAULT_HEALTH
        if args.health or health_path.exists():
            try:
                health = health_mod.load_report(health_path)
            except (health_mod.HealthError, OSError) as exc:
                health_error = str(exc)
        out = Path(args.out)
        write_text_atomic(out, render(manifest, health=health, health_error=health_error))
    except (manifest_mod.ManifestError, OSError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1
    snap = manifest.get("snapshot") or {}
    fresh = age_mod.freshness(snap) if snap else None
    result = {"ok": True, "path": str(out), "tool_count": manifest["tool_count"],
              "snapshot": snap.get("captured_at"),
              "freshness": fresh["summary"] if fresh else "no snapshot",
              "health": (health["verdict"] if health else
                         f"not shown: {health_error}" if health_error else "not provided"),
              "component_states": snap.get("component_states", {}),
              "install_states": snap.get("install_states", {})}
    if capture_result is not None:
        result["capture"] = capture_result
        result["ok"] = not capture_result["errors"]
    print(json.dumps(result, sort_keys=True))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    sys.exit(main())
