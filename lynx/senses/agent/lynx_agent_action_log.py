#!/usr/bin/env python3
"""S5 agent view: log Lynx's own actions to the ``noobia-agent`` view.

This is NOT a sense. The contract (ARCHITECTURE §3, loop guard #1) is
that Lynx's own actions go to the ``noobia-agent`` view - never to
``noobia-sense`` - so the trigger can never be set off by Lynx's own
doing. This module is the single writer for that view on Lynx:

- one bounded line per action: ``agent tool=<name> <detail>``
  (plain text, one line, at most 512 bytes);
- logged at ``user.info`` under the syslog ident ``noobia-agent``,
  which on Lynx lands in ``/var/log/lynx/messages`` where the view
  reader (the autonomy harness, V1) finds it by tag;
- no sense-line format, no NOOBIA prefix, no priority - on purpose.

Intended wiring (owner: the lynx_agent.py maintainers, in an IS packet -
this module does not patch their file): inside ``audit(event)``, add

    emit_action(event.get("tool", "agent_job"), summary)

so every agent job decision also lands in the view. The JSONL audit
file stays the detailed record; the view carries the human-readable
trace.

    lynx-agent-action TOOL [DETAIL ...]     # one action line
    python3 lynx_agent_action_log.py battery_status "checked capacity"
"""

from __future__ import annotations

import argparse
import re
import syslog

IDENT = "noobia-agent"
LEVEL = syslog.LOG_INFO
MAX_LINE_BYTES = 512
TOOL_RE = re.compile(r"^[a-z0-9_]{1,48}$")


def action_line(tool: str, detail: str = "") -> str:
    """Build one bounded, single-line action record. Raises ValueError
    on a bad tool name or an over-long detail (no silent truncation of
    the tool name; detail is trimmed on byte boundaries)."""
    if not isinstance(tool, str) or not TOOL_RE.match(tool):
        raise ValueError(f"tool must match ^[a-z0-9_]{{1,48}}$, got {tool!r}")
    line = f"agent tool={tool}"
    if detail:
        line += " " + re.sub(r"\s+", " ", str(detail)).strip()
    raw = line.encode("utf-8")
    if len(raw) > MAX_LINE_BYTES:
        budget = MAX_LINE_BYTES
        cut = line[:budget]
        while len(cut.encode("utf-8")) > budget and cut:
            cut = cut[:-1]
        line = cut
    return line


def syslog_writer(ident: str, level: int, message: str) -> None:
    """The default writer: one bounded line to syslog under the
    given ident. Never raises for a missing daemon (Lynx has BusyBox
    syslogd; on a test box without one the line is still returned by
    emit_action, which is the honest contract)."""
    syslog.openlog(ident, 0, syslog.LOG_USER)
    syslog.syslog(level, message)
    syslog.closelog()


def emit_action(tool: str, detail: str = "", writer=None) -> str:
    """Log one action to the noobia-agent view. ``writer`` is
    injectable for tests; the default writes to syslog under the
    noobia-agent ident. Returns the line that was logged."""
    line = action_line(tool, detail)
    if writer is None:
        try:
            syslog_writer(IDENT, LEVEL, line)
        except Exception:
            pass  # no syslog available: the line is still reported
    else:
        writer(IDENT, LEVEL, line)
    return line


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Log one of Lynx's own actions to the noobia-agent view.")
    parser.add_argument("tool", help="the action name, e.g. battery_status")
    parser.add_argument("detail", nargs="*", help="short description words")
    args = parser.parse_args(argv)
    import json
    try:
        line = emit_action(args.tool, " ".join(args.detail))
    except ValueError as exc:
        print(json.dumps({"ok": False, "error": "bad-action",
                          "detail": str(exc)[:200]}))
        return 1
    print(json.dumps({"ok": True, "ident": IDENT, "line": line}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
