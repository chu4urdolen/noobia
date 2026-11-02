#!/usr/bin/env python3
"""Stream Lynx's read-only /dev/kmsg to a bounded Nexus-side trial receipt."""

import argparse
import json
import os
from pathlib import Path
import select
import subprocess
import time

from lynx_wifi_v19_contact import ssh_command

ROOT = Path(__file__).resolve().parent.parent
HOST = "192.168.100.107"
PORT = "2222"
MAX_BYTES = 8 * 1024 * 1024


def remote(command, timeout=15):
    argv = ssh_command(HOST, command)
    argv[-2:-2] = ["-p", PORT]
    return subprocess.run(argv, capture_output=True, text=True, timeout=timeout,
                          check=True).stdout.strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration-seconds", type=int, default=180)
    args = parser.parse_args()
    if not 5 <= args.duration_seconds <= 600:
        parser.error("duration must be 5..600 seconds")
    os.umask(0o077)
    out = ROOT / "logs" / f"kernel-trial-{time.time_ns()}"
    out.mkdir(mode=0o700)
    result = {"schema": 1, "mode": "read-only-dev-kmsg-stream",
              "host": HOST, "duration_seconds": args.duration_seconds,
              "max_bytes": MAX_BYTES, "started_unix_ns": time.time_ns()}
    try:
        identity = remote("cat /proc/sys/kernel/random/boot_id; uname -r").splitlines()
        if len(identity) != 2 or identity[1] != "5.10.149-android12-9-o-g311738fbb5a8":
            raise RuntimeError("unexpected Lynx identity")
        result.update(boot_id=identity[0], kernel=identity[1])
        argv = ssh_command(HOST, f"/bin/busybox timeout {args.duration_seconds + 5} "
                                      "/bin/cat /dev/kmsg")
        argv[-2:-2] = ["-p", PORT]
        proc = subprocess.Popen(argv, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, start_new_session=True)
        deadline = time.monotonic() + args.duration_seconds
        count = 0
        try:
            with (out / "kernel.kmsg").open("wb") as sink:
                while time.monotonic() < deadline and count < MAX_BYTES:
                    ready, _, _ = select.select([proc.stdout], [], [], 0.5)
                    if ready:
                        data = os.read(proc.stdout.fileno(), min(65536, MAX_BYTES - count))
                        if not data:
                            break
                        sink.write(data)
                        sink.flush()
                        count += len(data)
                    elif proc.poll() is not None:
                        break
            result["bytes"] = count
            result["limit_reached"] = count >= MAX_BYTES
        finally:
            if proc.poll() is None:
                proc.terminate()
            try:
                _, stderr = proc.communicate(timeout=4)
            except subprocess.TimeoutExpired:
                proc.kill()
                _, stderr = proc.communicate(timeout=4)
            (out / "ssh.stderr").write_bytes(stderr[-16384:])
            result["ssh_exit"] = proc.returncode
        try:
            after = remote("cat /proc/sys/kernel/random/boot_id")
            result["same_boot_after"] = after == result["boot_id"]
        except (subprocess.SubprocessError, OSError):
            result["same_boot_after"] = None
        result["state"] = "captured" if count else "no-kernel-data"
    except Exception as exc:
        result.update(state="error", error=str(exc))
    result["finished_unix_ns"] = time.time_ns()
    (out / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"state": result["state"], "receipt": str(out / "result.json"),
                      "bytes": result.get("bytes", 0)}))
    if result["state"] != "captured":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
