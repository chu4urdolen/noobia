#!/usr/bin/env python3
"""On-demand operator entry point: refresh Lynx's snapshot, check drift, render the board.

One bounded Nexus-side command that:
1. captures a status snapshot through the existing pinned-SSH broker
   (``lynx_status_snapshot.py``; fixed read-only commands, per-command
   timeouts, and a 60 s overall deadline);
2. checks source-versus-installed catalog drift (``lynx_catalog_diff.py``);
3. renders the static, script-free board, with ``state/health.json`` if
   present, written atomically;
4. prints one short JSON result.

The result gives the board path, which sources were captured and which
failed, the snapshot age and boot state, catalog drift, and health.

If nothing can be captured, the previous snapshot is kept and the board is
rendered from it with its stale warning, and the result says so. ``--offline``
skips SSH entirely and renders from the saved snapshot.

No new transport, no periodic service, no browser server, no phone writes.

  lynx_board_refresh.py              # capture, diff, render
  lynx_board_refresh.py --offline    # saved snapshot only

Exit status: 0 complete and current; 2 rendered with a problem (partial
capture, capture failed, stale, rebooted, drift); 1 nothing rendered.
"""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import lynx_catalog_diff as diff_mod  # noqa: E402
import lynx_health_view as health_mod  # noqa: E402
import lynx_snapshot_age as age_mod  # noqa: E402
import lynx_status_snapshot as snap_mod  # noqa: E402
import lynx_tool_board as board_mod  # noqa: E402
import lynx_tool_manifest as manifest_mod  # noqa: E402

DEADLINE_S = 60


def with_deadline(runner, seconds=DEADLINE_S, clock=time.monotonic):
    """Stop starting new remote commands once the overall deadline has passed."""
    end = clock() + seconds

    def run(remote):
        if clock() >= end:
            return 124, b"", b"skipped: overall deadline reached"
        return runner(remote)
    return run


def refresh(status_path, board_path, health_path=None, offline=False,
            runner=snap_mod.ssh_runner, now=None, deadline_s=DEADLINE_S):
    status_path, board_path = Path(status_path), Path(board_path)
    result = {"mode": "offline" if offline else "live", "board": str(board_path),
              "snapshot": str(status_path)}
    problems = []

    if not offline:
        snapshot = snap_mod.capture(with_deadline(runner, deadline_s))
        captured = [n for n in snap_mod.COMMANDS if n in snapshot]
        result["sources"] = {"captured": captured, "errors": snapshot["errors"]}
        if captured:
            snapshot = snap_mod.with_previous(snapshot, status_path)
            snap_mod.write_atomic(status_path, snapshot)
            if snapshot["errors"]:
                problems.append("partial capture")
        else:
            problems.append("capture failed; showing previous snapshot")
    if not status_path.exists():
        result.update(ok=False, problems=problems + ["no snapshot to render"])
        return result, 1

    try:
        snapshot = manifest_mod.load_snapshot(status_path)
        manifest = manifest_mod.apply_snapshot(manifest_mod.build(), snapshot)
    except (manifest_mod.ManifestError, OSError) as exc:
        result.update(ok=False, problems=problems + [f"snapshot unusable: {exc}"])
        return result, 1

    fresh = age_mod.freshness(snapshot, now)
    result["freshness"] = {"state": fresh["state"], "age_s": fresh["age_s"],
                           "captured_at": fresh["captured_at"], "boot_id": fresh["boot_id"],
                           "boot_state": fresh["boot_state"], "summary": fresh["summary"]}
    if not fresh["current"]:
        problems.append(f"snapshot {fresh['state']}")
    if fresh["boot_state"] == "changed_since_previous":
        problems.append("Lynx rebooted since previous snapshot")

    try:
        _, files, duplicates = diff_mod.load_catalog(status_path)
        catalog = diff_mod.diff(diff_mod.source_files(), files, duplicates, limit=10)
        result["catalog"] = {"in_sync": catalog["in_sync"],
                             "counts": {k: v for k, v in catalog["counts"].items() if v},
                             "not_in_sync": [e["tool"] for e in catalog["entries"]],
                             "rejected": catalog["rejected_entries"]["count"]}
        if not catalog["in_sync"]:
            problems.append("catalog drift")
    except (diff_mod.DiffError, OSError) as exc:
        result["catalog"] = {"in_sync": None, "error": str(exc)}
        problems.append("catalog not checked")

    health = health_error = None
    health_path = Path(health_path) if health_path else board_mod.DEFAULT_HEALTH
    if health_path.exists():
        try:
            health = health_mod.load_report(health_path)
        except (health_mod.HealthError, OSError) as exc:
            health_error = str(exc)
    if health:
        unknown = sum(1 for c in health["checks"] if c["status"] in ("unknown", "unrecognized"))
        result["health"] = {"verdict": health["verdict"],
                            "unknown_checks": unknown, "checks": len(health["checks"]),
                            "freshness": health_mod.freshness(health, now)["text"]}
    else:
        result["health"] = (f"not shown: {health_error}" if health_error else "not provided")

    board_mod.write_text_atomic(board_path, board_mod.render(
        manifest, now, health=health, health_error=health_error))
    result.update(ok=not problems, problems=problems,
                  component_states=manifest["snapshot"]["component_states"])
    return result, 0 if not problems else 2


def main(argv=None, runner=snap_mod.ssh_runner):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--status", default=str(snap_mod.DEFAULT_OUT))
    parser.add_argument("--out", default=str(board_mod.DEFAULT_OUT))
    parser.add_argument("--health", metavar="FILE")
    parser.add_argument("--offline", action="store_true",
                        help="no SSH: render from the saved snapshot")
    args = parser.parse_args(argv)
    try:
        result, code = refresh(args.status, args.out, args.health, args.offline, runner)
    except OSError as exc:
        result, code = {"ok": False, "problems": [f"{type(exc).__name__}: {exc}"]}, 1
    print(json.dumps(result, sort_keys=True))
    return code


if __name__ == "__main__":
    sys.exit(main())
