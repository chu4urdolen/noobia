#!/usr/bin/env python3
"""Bounded helpers for Aria's Lynx work: run one pinned-SSH command and digest the newest trial result.

Replaces the repeated `ssh_command(...)` + `-p 2222` boilerplate and the
"newest result.json" Python heredocs seen in the Review Lynx handoff session.

  lynx_remote.py run "printf 'BATTERY\\n'; /usr/local/bin/lynx-status" [--timeout 20]
  lynx_remote.py result [--glob 'v53-bt-after-alpine-*'] [--limit 2]
"""

import argparse
import glob
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lynx_wifi_v19_contact import ssh_command  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
LOGS = ROOT / "logs"
DEFAULT_IP = "192.168.100.107"
DEFAULT_PORT = 2222
DEFAULT_MAX_OUTPUT = 12000


def _clip(text, limit):
    text = text or ""
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n[... clipped {len(text) - limit} chars]"


def cmd_run(args):
    """Run one command on Lynx over the pinned Alpine SSH link (port 2222 by default)."""
    argv = ssh_command(args.ip, args.command)
    argv[-2:-2] = ["-p", str(args.port)]
    try:
        result = subprocess.run(argv, capture_output=True, timeout=args.timeout)
    except subprocess.TimeoutExpired as exc:
        print(f"timeout after {args.timeout}s; remote command did not finish")
        out = exc.stdout or b""
        if out:
            print(_clip(out.decode(errors="replace"), args.max_output))
        return 124
    stdout = result.stdout.decode(errors="replace")
    stderr = result.stderr.decode(errors="replace").strip()
    print(f"exit={result.returncode}")
    print(_clip(stdout, args.max_output))
    if stderr:
        print("stderr:", _clip(stderr, min(2000, args.max_output)))
    return result.returncode if result.returncode < 255 else 255


def _digest(path):
    data = json.loads(path.read_text())
    steps = data.get("steps", [])
    samples = [s for s in steps if str(s.get("name", "")).startswith("health_sample")]
    nexus = data.get("nexus", {}) if isinstance(data.get("nexus"), dict) else {}
    mtime = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"path={path}")
    print(f"mtime={mtime}")
    for key in ("state", "boot_id", "watchdog_mode", "phone_ip", "candidate"):
        if key in data:
            print(f"{key}={data[key]}")
    if samples:
        print(f"health_samples={len(samples)} all_sample_exit_zero={all(s.get('exit') == 0 for s in samples)}")
    if nexus:
        print(f"nexus_state={nexus.get('state')}")
    if steps:
        print("final_steps=" + json.dumps([(s.get("name"), s.get("exit")) for s in steps[-4:]]))
    extra = {k: v for k, v in data.items()
             if k not in ("steps", "nexus", "state", "boot_id", "watchdog_mode",
                          "phone_ip", "candidate") and isinstance(v, (str, int, float, bool))}
    if extra:
        print("extra=" + json.dumps(extra))


def cmd_result(args):
    """Print a compact digest of the newest matching trial result.json file(s)."""
    pattern = str(LOGS) + "/" + args.glob.strip("/") + "/result.json"
    matches = sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)
    if not matches:
        print(f"no result.json matched {pattern}")
        return 1
    for path in matches[:args.limit]:
        _digest(Path(path))
        print("---")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="run one bounded command on Lynx via pinned SSH")
    run.add_argument("command")
    run.add_argument("--ip", default=DEFAULT_IP)
    run.add_argument("--port", type=int, default=DEFAULT_PORT)
    run.add_argument("--timeout", type=int, default=20)
    run.add_argument("--max-output", type=int, default=DEFAULT_MAX_OUTPUT)
    run.set_defaults(func=cmd_run)
    res = sub.add_parser("result", help="digest the newest trial result.json under lynx/logs")
    res.add_argument("--glob", default="*", help="directory glob under lynx/logs (default: all)")
    res.add_argument("--limit", type=int, default=1)
    res.set_defaults(func=cmd_result)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
