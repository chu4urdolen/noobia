#!/usr/bin/env python3
"""Orderly, identity-checked shutdown of Lynx over her pinned Wi-Fi SSH.

Run `python3 /noobia/lynx/tools/lynx_poweroff.py --check` to inspect the
target, then run without --check to request poweroff. No sudo is needed on
Nexus. This script only works while Lynx's Alpine SSH is available.
"""

import argparse
import json
import os
from pathlib import Path
import subprocess
import time

from lynx_wifi_v19_contact import ssh_command


ROOT = Path(__file__).resolve().parent.parent
IP = "192.168.100.8"
EXPECTED_KERNEL = "5.10.149-android12-9-o-g311738fbb5a8"
EXPECTED_INIT_SHA = "ebc6bb746aaf710d915c47036f92ce0c4ed23a185dfb5349b90e654bab7ba4ae"


def ssh(command, port=22, timeout=12):
    args = ssh_command(IP, command)
    args[-2:-2] = ["-p", str(port)]
    try:
        return subprocess.run(args, capture_output=True, text=True,
                              timeout=timeout)
    except subprocess.TimeoutExpired:
        return None


def checked_stdout(proc, label):
    if proc is None:
        raise RuntimeError(f"{label}: timed out")
    if proc.returncode != 0:
        raise RuntimeError(f"{label}: {proc.stderr.strip() or 'SSH failed'}")
    return proc.stdout.strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="verify identity and readiness without shutting down")
    args = parser.parse_args()
    os.umask(0o077)
    out = ROOT / "logs" / f"lynx-poweroff-{time.time_ns()}"
    out.mkdir(mode=0o700)
    result = {"state": "starting", "target": IP, "dry_run": args.check,
              "created_ns": time.time_ns()}
    try:
        rescue = checked_stdout(ssh(
            "set -eu; cat /proc/sys/kernel/random/boot_id; uname -r; "
            "sha256sum /init | cut -c1-64"), "rescue identity").splitlines()
        if len(rescue) != 3 or rescue[1] != EXPECTED_KERNEL or rescue[2] != EXPECTED_INIT_SHA:
            raise RuntimeError("Lynx V47 kernel or rescue image did not match")
        result["boot_id"] = rescue[0]
        alpine = checked_stdout(ssh(
            "set -eu; cat /proc/sys/kernel/random/boot_id; "
            "tr '\\000' ' ' </proc/1/cmdline; echo; "
            "command -v openrc-shutdown; "
            "/usr/local/bin/lynx-status --assert-ready",
            port=2222), "Alpine identity").splitlines()
        if len(alpine) < 4 or alpine[0] != rescue[0] or alpine[1].strip() != "/sbin/openrc-init":
            raise RuntimeError("Alpine PID 1 or boot ID did not match")
        if alpine[2] != "/sbin/openrc-shutdown":
            raise RuntimeError("OpenRC shutdown command is unavailable")
        result["health"] = json.loads(alpine[3])
        checked_stdout(ssh("/sbin/openrc-shutdown -D -p now", port=2222),
                       "OpenRC dry run")
        result["state"] = "checked"
        if args.check:
            print(f"Lynx ready to power off: boot {rescue[0]}, "
                  f"battery {result['health']['battery']['capacity_percent']}%")
        else:
            # Sync first. OpenRC then stops services and requests hardware
            # poweroff; an SSH disconnect during that process is expected.
            checked_stdout(ssh("sync", port=2222, timeout=25), "filesystem sync")
            result["shutdown_requested_ns"] = time.time_ns()
            command = ssh("/sbin/openrc-shutdown -p now", port=2222, timeout=20)
            result["shutdown_ssh_exit"] = command.returncode if command else None
            result["shutdown_stdout"] = command.stdout.strip() if command else ""
            result["shutdown_stderr"] = command.stderr.strip() if command else "timeout"
            result["state"] = "shutdown-request-sent"
            # Wi-Fi disappearing is useful evidence, but cannot by itself
            # prove that the hardware has fully powered off.
            misses = 0
            for _ in range(20):
                probe = ssh("cat /proc/sys/kernel/random/boot_id", timeout=5)
                if probe and probe.returncode == 0:
                    misses = 0
                    if probe.stdout.strip() != rescue[0]:
                        result["state"] = "different-boot-observed"
                        break
                else:
                    misses += 1
                    if misses >= 3:
                        result["state"] = "ssh-gone-after-shutdown-request"
                        break
                time.sleep(3)
            print("Shutdown requested; Lynx SSH is gone. Check the phone itself "
                  "to confirm it stayed off." if result["state"] ==
                  "ssh-gone-after-shutdown-request" else
                  f"Shutdown requested; result: {result['state']}. Check the phone.")
    except Exception as exc:
        result.update(state="failed", error=str(exc))
        print(f"Lynx poweroff failed: {exc}")
    finally:
        result["finished_ns"] = time.time_ns()
        path = out / "result.json"
        path.write_text(json.dumps(result, indent=2) + "\n")
        print(f"Receipt: {path}")
    if result["state"] not in ("checked", "ssh-gone-after-shutdown-request"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
