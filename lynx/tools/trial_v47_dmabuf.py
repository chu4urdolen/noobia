#!/usr/bin/env python3
"""One bounded V47 DMA-BUF display trial with durable host-side evidence.

The DRM program and stock display modules must already be staged. This tool
never writes boot partitions, never retries a modeset, and captures a reboot's
pstore before continuing diagnosis.
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
PROGRAM = "/var/lib/lynx-devroot/tmp/lynx_drm_dmabuf_pattern"


def ssh(command, port=2222, timeout=20):
    argv = ssh_command(IP, command)
    argv[-2:-2] = ["-p", str(port)]
    try:
        run = subprocess.run(argv, capture_output=True, timeout=timeout)
        return {"exit": run.returncode, "stdout": run.stdout, "stderr": run.stderr}
    except subprocess.TimeoutExpired as exc:
        return {"exit": None, "timeout": True, "stdout": exc.stdout or b"",
                "stderr": exc.stderr or b""}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--show-seconds", type=int, choices=range(1, 16), metavar="1..15",
                        required=True)
    args = parser.parse_args()
    os.umask(0o077)
    out = ROOT / "logs" / f"v47-dmabuf-trial-{time.time_ns()}"
    out.mkdir(mode=0o700)
    report = {"state": "starting", "boot_partition_writes": False,
              "show_seconds": args.show_seconds, "steps": []}

    def step(name, command, port=2222, timeout=20):
        result = ssh(command, port=port, timeout=timeout)
        (out / f"{name}.stdout").write_bytes(result.pop("stdout"))
        (out / f"{name}.stderr").write_bytes(result.pop("stderr"))
        result["name"] = name
        report["steps"].append(result)
        return result

    try:
        identity = step("identity", "cat /proc/sys/kernel/random/boot_id; uname -r; "
                        "sha256sum /init", port=22)
        lines = (out / "identity.stdout").read_text().splitlines()
        if identity["exit"] != 0 or len(lines) != 3 or \
           lines[1] != "5.10.149-android12-9-o-g311738fbb5a8" or \
           not lines[2].startswith("ebc6bb746aaf710d915c47036f92ce0c4ed23a185dfb5349b90e654bab7ba4ae"):
            raise RuntimeError("target is not the pinned V47 rescue and kernel")
        boot_id = lines[0]
        report["boot_id"] = boot_id
        preflight = step("preflight", "set -eu; "
                         f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{boot_id}"; '
                         "grep -q '^mtk_mml_mt6983 ' /proc/modules; "
                         "test -c /dev/dri/card0; "
                         "test \"$(cat /sys/class/drm/card0-DSI-1/status)\" = connected; "
                         "/usr/local/bin/lynx-status --assert-ready")
        if preflight["exit"] != 0:
            raise RuntimeError("display topology, card, or Alpine health preflight failed")
        health = json.loads((out / "preflight.stdout").read_text())
        report["battery_percent"] = health["battery"]["capacity_percent"]
        report["thermal_max_mC"] = health["thermal"]["max_mC"]
        if health["battery"]["capacity_percent"] < 45 or \
           health["battery"]["temperature_mC"] >= 30000 or \
           health["thermal"]["max_mC"] >= 45000:
            raise RuntimeError("battery or temperature outside display trial guard")
        # One CRTC modeset only. Capture both streams even if SSH drops.
        display = step("show", "/bin/busybox timeout 12 " + PROGRAM +
                       f" --show {args.show_seconds}", timeout=20)
        report["show_exit"] = display["exit"]
        report["show_timeout"] = display.get("timeout", False)
        after = step("after", "cat /proc/sys/kernel/random/boot_id; "
                     "/usr/local/bin/lynx-status --assert-ready", timeout=10)
        if after["exit"] == 0:
            report["state"] = "same-boot-after-trial"
        else:
            report["state"] = "connection-lost-waiting-for-reboot"
            deadline = time.monotonic() + 300
            while time.monotonic() < deadline:
                probe = step("reboot-probe", "cat /proc/sys/kernel/random/boot_id", port=22,
                             timeout=8)
                if probe["exit"] == 0:
                    new_boot = (out / "reboot-probe.stdout").read_text().strip()
                    if new_boot != boot_id:
                        report["new_boot_id"] = new_boot
                        for name in ("console-ramoops-0", "pmsg-ramoops-0"):
                            step(name, f"cat /sys/fs/pstore/{name}", port=22, timeout=20)
                        report["state"] = "reboot-pstore-captured"
                        break
                time.sleep(10)
    except Exception as exc:
        report.update(state="stopped", error=str(exc))
    finally:
        report["finished_ns"] = time.time_ns()
        path = out / "result.json"
        path.write_text(json.dumps(report, indent=2) + "\n")
        print(path, flush=True)
    if report["state"] == "stopped":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
