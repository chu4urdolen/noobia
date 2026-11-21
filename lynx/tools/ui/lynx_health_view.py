"""Read-only board section for Dushich's portable-health report (optional input).

Consumes a *saved* report produced by ``lynx/tools/health/portable_health.py``
or ``lynx_health_collect.py --evaluate`` (schema ``portable-health/1``). It
never runs the collector or evaluator, never contacts Lynx, and never edits
``lynx/tools/health/``.

Rules:
- ``ok``, ``warn``, ``fail`` and ``unknown`` are shown exactly; any other
  status is shown as ``unrecognized``, never as ok;
- missing values are not invented;
- thresholds are Dushich's proposals, not validated Lynx limits, and the
  section says so;
- health never changes the phone-reported validation shown elsewhere.
"""

from datetime import datetime, timezone
import html
import json
from pathlib import Path

import lynx_snapshot_age as age_mod

SCHEMA = "portable-health/1"
STATUSES = ("ok", "warn", "fail", "unknown")
MAX_BYTES = 256 * 1024
MAX_CHECKS = 50
EVIDENCE_CHARS = 160


class HealthError(Exception):
    pass


def esc(value):
    return html.escape(str(value), quote=True)


def _status(value):
    return value if value in STATUSES else "unrecognized"


def load_report(path):
    path = Path(path)
    if path.stat().st_size > MAX_BYTES:
        raise HealthError(f"health report exceeds {MAX_BYTES} bytes")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError) as exc:
        raise HealthError(f"health report is not JSON: {exc}") from None
    return normalize(data)


def normalize(data):
    """Validate a report; return a bounded, display-safe copy."""
    if not isinstance(data, dict):
        raise HealthError("health report is not a JSON object")
    if data.get("schema") != SCHEMA:
        raise HealthError(f"unsupported health schema {str(data.get('schema'))[:40]!r}; "
                          f"expected {SCHEMA}")
    if data.get("host") != "lynx":
        raise HealthError(f"health report is for host {str(data.get('host'))[:40]!r}, not lynx")
    checks = data.get("checks")
    if not isinstance(checks, list):
        raise HealthError("health report has no checks list")
    out = []
    for check in checks[:MAX_CHECKS]:
        if not isinstance(check, dict) or not isinstance(check.get("name"), str):
            out.append({"name": "(malformed check)", "status": "unrecognized",
                        "scope": "", "notes": [], "evidence": ""})
            continue
        evidence = check.get("evidence")
        text = json.dumps(evidence, sort_keys=True, ensure_ascii=False) if evidence else ""
        if len(text) > EVIDENCE_CHARS:
            text = text[:EVIDENCE_CHARS] + "…"
        notes = check.get("notes") if isinstance(check.get("notes"), list) else []
        out.append({"name": check["name"][:64], "status": _status(check.get("status")),
                    "scope": str(check.get("scope") or "")[:32],
                    "notes": [str(n)[:200] for n in notes[:5]], "evidence": text})
    return {"schema": SCHEMA, "host": "lynx",
            "captured_at": data.get("captured_at") if isinstance(data.get("captured_at"), str) else None,
            "verdict": _status(data.get("verdict")),
            "evaluator_stale": data.get("stale") is True,
            "checks": out, "checks_truncated": max(0, len(checks) - MAX_CHECKS)}


def parse_any_time(value):
    """ISO-8601 with Z or an offset (the health collector uses both)."""
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else None


def freshness(report, now=None):
    now = now or datetime.now(timezone.utc)
    captured = parse_any_time(report.get("captured_at"))
    if captured is None:
        return {"state": "unknown_time", "current": False, "text": "capture time unknown"}
    seconds = int((now - captured).total_seconds())
    if seconds < -age_mod.CLOCK_SKEW_S:
        return {"state": "future", "current": False, "text": "capture time is in the future"}
    seconds = max(seconds, 0)
    if seconds > age_mod.MAX_AGE_S or report.get("evaluator_stale"):
        return {"state": "stale", "current": False,
                "text": f"STALE: {age_mod.age_text(seconds)}"}
    return {"state": "fresh", "current": True, "text": age_mod.age_text(seconds)}


def _unknown_note(report):
    unknown = sum(1 for c in report["checks"] if c["status"] in ("unknown", "unrecognized"))
    if not unknown:
        return ""
    return (f' · <strong>{unknown} of {len(report["checks"])} checks unknown or '
            'unrecognized</strong> (the verdict does not cover them)')


def section(report, now=None, error=None):
    """HTML for the health section; ``error`` renders an explanation instead."""
    out = ['<section aria-labelledby="health"><h2 id="health">'
           'Health (Dushich\'s portable evaluator)</h2>']
    if error:
        out.append(f'<div class="warn-box" role="status">Health report not shown: '
                   f'{esc(error)}</div></section>')
        return "".join(out)
    fresh = freshness(report, now)
    out.append(f'<p class="sub" data-health-freshness="{esc(fresh["state"])}">'
               f'Report {esc(report["captured_at"] or "time unknown")} · {esc(fresh["text"])} · '
               f'verdict <span class="badge h-{esc(report["verdict"])}">'
               f'<span class="sr">Health verdict: </span>{esc(report["verdict"])}</span>'
               + _unknown_note(report) + '</p>')
    if not fresh["current"]:
        out.append(f'<div class="warn-box" role="status">{esc(fresh["text"])}. These health '
                   'results describe capture time, not now.</div>')
    out.append('<p class="legend">Thresholds are Dushich\'s proposals, not validated Lynx '
               'limits. Missing facts stay <em>unknown</em>. Health results never change '
               'the phone-reported validation above.</p><ul class="evidence-list">')
    for check in report["checks"]:
        notes = "; ".join(check["notes"])
        out.append('<li class="evidence health-check">'
                   f'<p><span class="badge h-{esc(check["status"])}"><span class="sr">'
                   f'Health: </span>{esc(check["status"])}</span> '
                   f'<strong>{esc(check["name"])}</strong>'
                   + (f' <span class="meta">({esc(check["scope"])})</span>' if check["scope"] else "")
                   + "</p>"
                   + (f'<p class="next">{esc(notes)}</p>' if notes else "")
                   + (f'<p class="meta">{esc(check["evidence"])}</p>' if check["evidence"] else "")
                   + "</li>")
    if report["checks_truncated"]:
        out.append(f'<li class="meta">{report["checks_truncated"]} more checks not shown</li>')
    out.append("</ul></section>")
    return "".join(out)


CSS = """
.h-ok{background:var(--ok-bg);color:var(--ok)}
.h-warn{background:var(--warn-bg);color:var(--warn)}
.h-fail,.h-unrecognized{background:var(--bad-bg);color:var(--bad)}
.h-unknown{background:var(--na-bg);color:var(--na)}
"""
