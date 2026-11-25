#!/usr/bin/env python3
"""lynx-security-status: Lynx's own read-only security summary (LNX-88).

Rose's backlog, "Read-only agent security diagnostic tool" (Gwyn, 2026-11-25).
An agent tool: she can answer "are you safe?" from facts. It runs the
exposure and config audits and counts the last 24 hours of security
decisions. It changes nothing and prints no secrets or arguments.

    lynx-security-status          a few short lines for her (and people)
    lynx-security-status --json   the full structure
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lynx_config_audit  # noqa: E402
import lynx_exposure_audit  # noqa: E402

LOGS = {
    # "cli" decisions are people and the regression suite checking the policy, not her tools.
    "network tool refusals": (Path("/var/log/lynx-tool-policy.jsonl"),
                              lambda r: r.get("allowed") is False and r.get("tool") != "cli"),
    "tool broker refusals": (Path("/var/log/lynx-tool-broker.jsonl"), lambda r: r.get("ok") is False),
    "security incidents (journal)": (Path("/var/log/lynx/security.jsonl"), lambda r: True),
}
SYSLOG = Path("/var/log/lynx/messages")
TAIL_BYTES = 2_000_000
DAY = 86400


def tail_lines(path: Path, limit: int = TAIL_BYTES) -> list[str]:
    try:
        with path.open("rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            fh.seek(max(0, size - limit))
            return fh.read().decode("utf-8", "replace").splitlines()
    except OSError:
        return []


def count_jsonl(path: Path, keep, since: float) -> int | None:
    if not path.exists():
        return None
    n = 0
    for line in tail_lines(path):
        try:
            r = json.loads(line)
        except ValueError:
            continue
        t = r.get("t") or r.get("time") or r.get("ts") or 0
        try:
            t = float(t)
        except (TypeError, ValueError):
            t = 0
        if (t == 0 or t >= since) and keep(r):
            n += 1
    return n


def status(now: float | None = None) -> dict:
    now = now or time.time()
    since = now - DAY
    exposure = lynx_exposure_audit.audit()
    config = lynx_config_audit.audit()
    counts = {name: count_jsonl(path, keep, since) for name, (path, keep) in LOGS.items()}
    # Injection attempts are sense lines (no timestamps in a parseable form): count the recent tail.
    counts["prompt injection or malicious messages (recent log)"] = sum(
        1 for l in tail_lines(SYSLOG) if "noobia-sense" in l and
        ("prompt.injection.suspected" in l or "message.suspicious" in l))
    high = [f for f in exposure["findings"] + config["findings"] if f["level"] == "high"]
    warn = [f for f in exposure["findings"] + config["findings"] if f["level"] == "warn"]
    return {"ok": not high, "listeners": [f"{l['service']} on port {l['port']}" for l in exposure["listeners"]],
            "high": [f["text"] for f in high], "warn": [f["text"] for f in warn],
            "boot_pins": config["facts"].get("boot_pins"), "last_24h": counts,
            "note": "read-only; observations, not proof of an attack"}


def text(s: dict) -> str:
    lines = [("I look safe: " if s["ok"] else "I need attention: ") +
             f"{len(s['listeners'])} doors open to the network ({'; '.join(s['listeners'])})."]
    if s["high"]:
        lines.append("Serious: " + " | ".join(s["high"][:3]))
    if s["warn"]:
        lines.append("To improve: " + " | ".join(w.split(':')[0] if len(w) > 90 else w for w in s["warn"][:4]))
    pins = s.get("boot_pins") or {}
    lines.append("My boot files " + ("match their pins." if set(pins.values()) == {"match"} else f"DO NOT match: {pins}."))
    seen = [f"{v} {k}" for k, v in s["last_24h"].items() if v]
    lines.append("Last day: " + (", ".join(seen) if seen else "no refusals, incidents or injection attempts") + ".")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    try:
        s = status()
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}))
        return 2
    print(json.dumps(s, indent=1) if args.json else text(s))
    return 0


if __name__ == "__main__":
    sys.exit(main())
