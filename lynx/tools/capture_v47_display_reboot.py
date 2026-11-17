"""Bounded, read-only capture after a V47 display probe interrupts SSH."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import time

from lynx_wifi_v19_contact import ssh_command


ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "logs" / f"v47-display-reboot-capture-{time.time_ns()}"


def ssh(command, port=22, timeout=8):
    args = ssh_command("192.168.100.8", command)
    args[-2:-2] = ["-p", str(port)]
    try:
        return subprocess.run(args, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old-boot-id", required=True,
                        help="boot ID observed immediately before the trial")
    args = parser.parse_args()
    os.umask(0o077)
    OUT.mkdir(mode=0o700)
    result = {"old_boot_id": args.old_boot_id, "samples": []}
    deadline = time.monotonic() + 300
    while time.monotonic() < deadline:
        probe = ssh("cat /proc/sys/kernel/random/boot_id; uptime")
        sample = {"time_ns": time.time_ns(), "port22_exit": probe.returncode if probe else None}
        if probe and probe.returncode == 0:
            sample["stdout"] = probe.stdout.decode(errors="replace")
            result["samples"].append(sample)
            observed_id = sample["stdout"].splitlines()[0]
            if observed_id != args.old_boot_id:
                result["new_boot_id"] = observed_id
                break
            time.sleep(10)
            continue
        result["samples"].append(sample)
        time.sleep(10)
    if "new_boot_id" in result:
        # Capture the raw retained crash log promptly, before another reboot.
        for name in ("console-ramoops-0", "pmsg-ramoops-0"):
            proc = ssh(f"cat /sys/fs/pstore/{name}", timeout=20)
            if proc:
                (OUT / name).write_bytes(proc.stdout)
                result[name] = {"exit_code": proc.returncode, "bytes": len(proc.stdout)}
        proc = ssh("dmesg | tail -n 250", timeout=20)
        if proc:
            (OUT / "new-boot-dmesg.txt").write_bytes(proc.stdout)
        for _ in range(15):
            proc = ssh("/usr/local/bin/lynx-status --assert-ready", port=2222)
            if proc and proc.returncode == 0:
                (OUT / "lynx-status.json").write_bytes(proc.stdout)
                result["alpine_healthy"] = True
                break
            time.sleep(10)
    (OUT / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(str(OUT / "result.json"), flush=True)


if __name__ == "__main__":
    main()
