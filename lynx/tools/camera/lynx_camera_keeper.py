#!/usr/bin/env python3
"""lynx-camera-keeper: prepare Lynx's camera after every boot, safely (Nexus side).

Lynx's CAMSV camera stack (patched ISP, sensor, route) lives in RAM and is
gone after every reboot. Tom (2026-11-22): "we need persistence". This keeper
runs on Nexus and, for each new Lynx boot:

1. waits until Lynx is reachable, up at least SETTLE_S seconds, and healthy;
2. writes a STARTED marker for that boot_id, runs the proven
   prepare_camera_camsv.py (Tom authorised it to run without a person
   present), and writes DONE or FAILED;
3. never retries a failed preparation in the same boot.

Boot-loop safety (Principle 10): if a boot ended with STARTED but neither
DONE nor FAILED - Lynx crashed or rebooted DURING preparation - the next
boot is SKIPPED, logged loudly, and stays camera-less until a person runs
the preparation by hand (or deletes the marker). A preparation that kills
her can therefore never become a loop.

State (Nexus): $NOOBIA/lynx/state/camera-keeper/<boot_id>.{started,done,failed,skipped}
Disable: touch $NOOBIA/lynx/state/camera-keeper/disable
Logs: stdout (journal of noobia-lynx-camera-keeper.service).

    lynx_camera_keeper.py --once     one decision, then exit
    lynx_camera_keeper.py            loop every --every seconds
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

NOOBIA = Path(os.environ.get("NOOBIA", "/noobia"))
TOOLS = NOOBIA / "lynx" / "tools"
STATE = Path(os.environ.get("LYNX_CAMERA_KEEPER_STATE", NOOBIA / "lynx" / "state" / "camera-keeper"))
PREPARE = TOOLS / "prepare_camera_camsv.py"
REMOTE = TOOLS / "lynx_remote.py"
SETTLE_S = 300
PREPARE_TIMEOUT_S = 900


def log(msg: str) -> None:
    print(f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} lynx-camera-keeper {msg}", flush=True)


def lynx(command: str, timeout: int = 25, run=subprocess.run) -> str | None:
    """Run one bounded command on Lynx; None if unreachable or it failed."""
    try:
        res = run([sys.executable, str(REMOTE), "run", command, "--timeout", str(timeout)],
                  capture_output=True, text=True, timeout=timeout + 15)
    except (OSError, subprocess.SubprocessError):
        return None
    if res.returncode != 0 or not res.stdout.startswith("exit=0"):
        return None
    return res.stdout.split("\n", 1)[1] if "\n" in res.stdout else ""


def marker(boot: str, kind: str) -> Path:
    return STATE / f"{boot}.{kind}"


def previous_boot_interrupted(current: str) -> str | None:
    """boot_id of the newest OTHER boot that started preparing and never finished."""
    starts = sorted(STATE.glob("*.started"), key=lambda p: p.stat().st_mtime, reverse=True)
    for s in starts:
        boot = s.name[:-len(".started")]
        if boot == current:
            continue
        if not (marker(boot, "done").exists() or marker(boot, "failed").exists()):
            return boot
        return None   # only the most recent other boot matters
    return None


def decide(read=lynx, prepare=None) -> str:
    """One step. Returns a short word for what happened (also logged)."""
    STATE.mkdir(parents=True, exist_ok=True)
    if (STATE / "disable").exists():
        return "disabled"
    out = read("cat /proc/sys/kernel/random/boot_id; cut -d. -f1 /proc/uptime; "
               "test -e /dev/video145 && echo PREPARED || echo NOT_PREPARED; "
               "/usr/local/bin/lynx-status --assert-ready >/dev/null 2>&1 && echo HEALTHY || echo UNHEALTHY; "
               "grep -q 'failures\" -ge 10' /run/lynx/lynx-health-supervisor.sh && "
               "! grep -q -E 'poweroff|reboot' /run/lynx/thermal-watch.sh /run/lynx/battery-watch.sh "
               "&& echo SAFE_WATCHERS || echo UNSAFE_WATCHERS; "
               "m=$(cut -d' ' -f1 /var/lib/noobia/power-mode 2>/dev/null); echo MODE_${m:-saving}")
    if out is None:
        return "unreachable"
    lines = out.split()
    if len(lines) < 6:
        return "unreadable"
    boot, uptime, prepared, healthy = lines[0], int(lines[1]) if lines[1].isdigit() else 0, lines[2], lines[3]
    safe = lines[4] == "SAFE_WATCHERS"
    active = lines[5] == "MODE_active"
    for kind in ("done", "failed", "skipped"):
        if marker(boot, kind).exists():
            return f"already-{kind}"
    if marker(boot, "started").exists():
        return "in-progress-or-interrupted"     # never start twice in one boot
    if prepared == "PREPARED":
        marker(boot, "done").write_text(json.dumps({"boot": boot, "note": "already prepared (by hand)"}))
        log(f"boot {boot[:8]} camera already prepared")
        return "already-prepared"
    bad = previous_boot_interrupted(boot)
    if bad:
        marker(boot, "skipped").write_text(json.dumps({"boot": boot, "interrupted_boot": bad}))
        log(f"SKIP boot {boot[:8]}: preparation on boot {bad[:8]} never finished (Lynx crashed or "
            f"rebooted during it). Not retrying automatically; prepare by hand once, or delete "
            f"{marker(bad, 'started')} to re-enable.")
        return "skipped-after-interrupted"
    if uptime < SETTLE_S:
        return "settling"
    if healthy != "HEALTHY":
        return "waiting-for-health"
    if not active:
        # Power saving (boot default, or a guard rested her): no camera prep.
        return "power-saving"
    if not safe:
        # 2026-11-23: camera heat + the boot image's original watchers (poweroff
        # on one 60 C reading or 3 health flickers) switched Lynx off. Never
        # prepare until lynx-watchers-swap has replaced them on this boot.
        return "waiting-for-safe-watchers"
    marker(boot, "started").write_text(json.dumps({"boot": boot, "t": time.time()}))
    os.sync()   # the STARTED marker must be on disk before anything can go wrong
    log(f"boot {boot[:8]}: preparing camera")
    result = (prepare or _prepare)()
    if result.get("state") in ("prepared_no_stream", "already_prepared"):
        marker(boot, "done").write_text(json.dumps(result))
        log(f"boot {boot[:8]}: camera prepared ({result.get('receipt')})")
        return "prepared"
    marker(boot, "failed").write_text(json.dumps(result))
    log(f"boot {boot[:8]}: preparation FAILED, not retrying this boot: {result.get('error')}")
    return "failed"


def _prepare() -> dict:
    try:
        res = subprocess.run([sys.executable, str(PREPARE), "--execute", "--attended"],
                             cwd=str(TOOLS), capture_output=True, text=True, timeout=PREPARE_TIMEOUT_S)
        return json.loads(res.stdout.strip().splitlines()[-1])
    except subprocess.TimeoutExpired:
        return {"state": "failed", "error": f"prepare timed out after {PREPARE_TIMEOUT_S}s"}
    except (OSError, ValueError, IndexError) as exc:
        return {"state": "failed", "error": f"prepare unusable: {type(exc).__name__}"}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--every", type=float, default=30.0)
    args = ap.parse_args(argv)
    if args.once:
        print(decide())
        return 0
    last = None
    while True:
        try:
            what = decide()
        except Exception as exc:    # the keeper itself must never die on one bad step
            what = f"error {type(exc).__name__}: {str(exc)[:120]}"
        if what != last:
            log(what)
            last = what
        time.sleep(max(10.0, args.every))


if __name__ == "__main__":
    sys.exit(main())
