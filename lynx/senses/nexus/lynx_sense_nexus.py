#!/usr/bin/env python3
"""S8 nexus sense for Lynx (PLAN.md): is the Nexus reachable?

Event sense, transitions only:
- up -> down   ->  NOOBIA P1 nexus unreachable host=... port=...
- down -> up   ->  NOOBIA P1 nexus reachable host=... port=...

Why it matters (ARCHITECTURE §5): Aigel lives on the Nexus; when Lynx
cannot reach her, the local routing fallback takes over and the Noob
should be able to see that. The sense makes the fallback visible.

Probe: one bounded TCP connect (3 s timeout, no application protocol,
no credentials) to the Nexus. Default target is the authenticated
inference proxy on 192.168.100.106:8080 - a long-lived service, unlike
Aigel's :112 which is not installed until IS-3 and would false-alarm.
Override with env NOOBIA_NEXUS_HOST / NOOBIA_NEXUS_PORT (or --host /
--port).

Hysteresis (no boot-time or flap alarms):
- a probe failure counts toward the alarm; the P1 goes out only after
  2 consecutive failures while previously up;
- the P1 is a transition: while down, nothing is re-emitted (the state
  file says so), and while up again, nothing repeats until the next
  transition;
- the very first sample after a boot (or state loss) only baselines.

    python3 /usr/local/lib/noobia/senses/nexus/lynx_sense_nexus.py [--dry-run]
"""

from __future__ import annotations

import argparse
import os
import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "common"))
from lynx_senses_lib import (  # noqa: E402
    NEXUS_DEFAULT_HOST,
    NEXUS_DEFAULT_PORT,
    NEXUS_FAIL_BEFORE_UNREACHABLE,
    NEXUS_PROBE_TIMEOUT_S,
    SenseUnavailable,
    base_result,
    emit_line,
    failure,
    finish,
    import_sense,
    load_state,
    now_ts,
    save_state,
    state_path,
)


def probe(host: str, port: int,
          timeout: float = NEXUS_PROBE_TIMEOUT_S) -> bool:
    """One bounded TCP connect. True on connect, False otherwise."""
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except OSError:
        return False


def run(dry_run: bool = False, state_file: str | None = None,
        host: str | None = None, port: int | None = None,
        probe_fn: "callable | None" = None,
        now: int | None = None) -> tuple[dict, int]:
    """One nexus probe. probe_fn(host, port) -> bool is injectable.
    Returns (result_dict, exit_code)."""
    t = int(now if now is not None else now_ts())
    try:
        sense = import_sense()
    except SenseUnavailable as exc:
        return failure("nexus", exc)

    host = host or os.environ.get("NOOBIA_NEXUS_HOST", NEXUS_DEFAULT_HOST)
    port = int(port or os.environ.get("NOOBIA_NEXUS_PORT", NEXUS_DEFAULT_PORT))
    up_now = (probe_fn or probe)(host, port)

    path = state_path("nexus", state_file)
    state = load_state(path)
    emitted: list[str] = []
    known = state.get("up") is not None

    if known and up_now:
        state["fail_count"] = 0
        if not state.get("up"):
            line = emit_line(
                sense, 1, "nexus", "reachable",
                fields={"host": host, "port": port},
                text="Nexus is reachable again", dry_run=dry_run)
            emitted.append(line)
            state["up"] = True
    elif known and not up_now:
        fails = int(state.get("fail_count", 0)) + 1
        state["fail_count"] = fails
        if state.get("up") and fails >= NEXUS_FAIL_BEFORE_UNREACHABLE:
            line = emit_line(
                sense, 1, "nexus", "unreachable",
                fields={"host": host, "port": port, "errors": fails},
                text="Nexus has been unreachable", dry_run=dry_run)
            emitted.append(line)
            state["up"] = False
    else:
        # First sample after boot/state loss: baseline only.
        state["up"] = bool(up_now)
        state["fail_count"] = 0 if up_now else 1

    state["t"] = t
    if not dry_run:
        save_state(path, state)
    return (base_result("nexus",
                        sampled={"host": host, "port": port, "up": up_now},
                        emitted=emitted, state=state), 0)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true",
                        help="print would-be sense lines; never write state or syslog")
    parser.add_argument("--state-file", default=None,
                        help="state file (default: /var/lib/noobia/senses/nexus/state.json)")
    parser.add_argument("--host", default=None,
                        help="Nexus host (default: env NOOBIA_NEXUS_HOST or 192.168.100.106)")
    parser.add_argument("--port", default=None, type=int,
                        help="Nexus port (default: env NOOBIA_NEXUS_PORT or 8080)")
    args = parser.parse_args(argv)
    try:
        result, code = run(dry_run=args.dry_run, state_file=args.state_file,
                           host=args.host, port=args.port)
    except (OSError, ValueError) as exc:
        result, code = failure("nexus", exc)
    return finish(result, code)


if __name__ == "__main__":
    sys.exit(main())
