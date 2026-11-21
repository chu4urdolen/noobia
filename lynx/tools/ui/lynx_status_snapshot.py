#!/usr/bin/env python3
"""Bounded, read-only status broker: capture one Lynx status snapshot.

Runs a fixed list of read-only commands on Lynx over the pinned Alpine SSH
link and saves their JSON as one snapshot for ``lynx_tool_manifest.py
--status`` and ``lynx_tool_board.py``:

- ``platform``   ``lynx-platform-status all``
- ``peripheral`` ``lynx-peripheral-status all``
- ``hardware``   ``lynx-hardware status all``
- ``catalog``    SHA-256 of the installed agent tool manifests and wrappers
- ``boot``       the kernel boot ID, so a reboot between snapshots is visible

When saving, the previous snapshot's boot ID and capture time are kept under
``previous`` so readers can tell that Lynx rebooted (RAM-loaded drivers gone).

The command list is a constant: no caller input reaches the remote shell.
Each command has a remote and a local timeout and a 256 KiB output cap. The
SSH login is root, so the list must stay read-only. Do not add a command here
that writes, actuates, loads a module, or touches the modem or SIM. Nothing
else is written on Nexus beyond the snapshot file (replaced atomically).

  lynx_status_snapshot.py               # capture to state/latest.json
  lynx_status_snapshot.py --out FILE    # capture elsewhere
  lynx_status_snapshot.py --print       # capture and print the snapshot only

Exit status: 0 all sources captured, 2 partial, 1 nothing captured or error.
"""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

STATE_DIR = HERE / "state"
DEFAULT_OUT = STATE_DIR / "latest.json"
HOST = "192.168.100.107"
PORT = 2222
REMOTE_TIMEOUT_S = 10
LOCAL_TIMEOUT_S = 20
MAX_OUTPUT = 256 * 1024
CATALOG_DIR = "/usr/local/share/lynx/agent-tools"

COMMANDS = {
    "platform": "/usr/bin/python3 /usr/local/bin/lynx-platform-status all",
    "peripheral": "/usr/bin/python3 /usr/local/bin/lynx-peripheral-status all",
    "hardware": "/usr/bin/python3 /usr/local/bin/lynx-hardware status all",
    "catalog": f"cd {CATALOG_DIR} && sha256sum -- *.json *.sh",
    "boot": "cat /proc/sys/kernel/random/boot_id",
}
BOOT_LINE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
CATALOG_LINE = re.compile(r"^([0-9a-f]{64})  ([a-z][a-z0-9_]{0,63}\.(?:json|sh))$")


class CaptureError(Exception):
    pass


def ssh_runner(remote, host=HOST, port=PORT):
    """Run one remote command over the pinned SSH link; return (rc, out, err)."""
    from lynx_wifi_v19_contact import ssh_command
    argv = ssh_command(host, f"timeout {REMOTE_TIMEOUT_S} sh -c {quote(remote)}")
    argv[-2:-2] = ["-p", str(port)]
    try:
        proc = subprocess.run(argv, capture_output=True, timeout=LOCAL_TIMEOUT_S,
                              stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return 124, b"", b"local timeout"
    return proc.returncode, proc.stdout, proc.stderr


def quote(text):
    return "'" + text.replace("'", "'\\''") + "'"


def parse_catalog(text):
    files = {}
    for line in text.splitlines():
        match = CATALOG_LINE.match(line)
        if not match:
            raise CaptureError(f"unexpected catalog line: {line[:80]!r}")
        if match.group(2) in files:
            raise CaptureError(f"duplicate catalog entry: {match.group(2)}")
        files[match.group(2)] = match.group(1)
    if not files:
        raise CaptureError("installed catalog is empty")
    return {"dir": CATALOG_DIR, "files": dict(sorted(files.items()))}


def parse_source(name, raw):
    if len(raw) > MAX_OUTPUT:
        raise CaptureError(f"output exceeds {MAX_OUTPUT} bytes")
    try:
        text = raw.decode("utf-8")
    except UnicodeError:
        raise CaptureError("output is not UTF-8") from None
    if name == "catalog":
        return parse_catalog(text)
    if name == "boot":
        value = text.strip()
        if not BOOT_LINE.fullmatch(value):
            raise CaptureError("boot ID is not a UUID")
        return {"boot_id": value}
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise CaptureError(f"output is not JSON: {exc}") from None
    if not isinstance(data, dict):
        raise CaptureError("output is not a JSON object")
    return data


def capture(runner=ssh_runner, now=None):
    snapshot = {"captured_at": (now or datetime.now(timezone.utc)).strftime(
                    "%Y-%m-%dT%H:%M:%SZ"),
                "host": HOST, "route": "pinned-ssh", "errors": {}}
    for name, remote in COMMANDS.items():
        try:
            rc, out, err = runner(remote)
            if rc != 0:
                detail = (err or b"").decode("utf-8", "replace").strip()[:200]
                raise CaptureError(f"exit {rc}" + (f": {detail}" if detail else ""))
            snapshot[name] = parse_source(name, out)
        except CaptureError as exc:
            snapshot["errors"][name] = str(exc)
        except OSError as exc:
            snapshot["errors"][name] = f"{type(exc).__name__}: {exc.strerror or exc}"
    return snapshot


def with_previous(snapshot, path):
    """Record the boot ID and time of the snapshot about to be replaced."""
    try:
        old = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return snapshot
    if not isinstance(old, dict):
        return snapshot
    boot = old.get("boot")
    previous = {
        "boot_id": boot.get("boot_id") if isinstance(boot, dict) else None,
        "captured_at": old.get("captured_at") if isinstance(old.get("captured_at"), str) else None,
    }
    return dict(snapshot, previous=previous)


def write_atomic(path, snapshot):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".snapshot-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(snapshot, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def main(argv=None, runner=ssh_runner):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="snapshot path")
    parser.add_argument("--print", dest="print_only", action="store_true",
                        help="print the snapshot instead of saving it")
    args = parser.parse_args(argv)
    snapshot = capture(runner)
    captured = [name for name in COMMANDS if name in snapshot]
    code = 0 if len(captured) == len(COMMANDS) else (2 if captured else 1)
    if args.print_only:
        print(json.dumps(snapshot, sort_keys=True))
        return code
    if captured:
        try:
            snapshot = with_previous(snapshot, args.out)
            write_atomic(args.out, snapshot)
        except OSError as exc:
            print(json.dumps({"ok": False, "error": f"cannot write {args.out}: {exc}"}))
            return 1
    boot = snapshot.get("boot") or {}
    previous = snapshot.get("previous") or {}
    print(json.dumps({"ok": code == 0, "captured": captured,
                      "errors": snapshot["errors"], "captured_at": snapshot["captured_at"],
                      "boot_id": boot.get("boot_id"),
                      "rebooted_since_previous": (
                          None if not (boot.get("boot_id") and previous.get("boot_id"))
                          else boot["boot_id"] != previous["boot_id"]),
                      "path": args.out if captured else None}, sort_keys=True))
    return code


if __name__ == "__main__":
    sys.exit(main())
