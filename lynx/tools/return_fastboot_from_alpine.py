#!/usr/bin/env python3
"""One guarded V50 Alpine to Fastboot RESTART2 request; no partition write."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time

from lynx_wifi_v19_contact import ssh_command
from lynx_presence import usb_probe
from lynx_fastboot_preflight import FASTBOOT, SERIAL


ROOT = Path(__file__).resolve().parent.parent
HELPER = ROOT / "linux-port/artifacts/boot-proof-reboot.elf"
HELPER_SHA = "e07fbe2825b8283f8c58f7f55eaf143fe9d983bd05c7478b659840dff36f8d08"
V50_SHA = "6168cd6288679a321a4d8bc41c7d3dde64a49d3cfe855b8e44542f3307fd5a59"
REMOTE = "/run/lynx/fastboot-return-helper"


def phone(command, payload=None, timeout=15):
    argv = ssh_command("192.168.100.107", command)
    argv[-2:-2] = ["-p", "2222"]
    return subprocess.run(argv, input=payload, capture_output=True, timeout=timeout)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="request live Fastboot reboot")
    args = parser.parse_args()
    if not args.execute:
        parser.error("live reboot requires --execute")
    receipt = ROOT / "logs" / f"v50-alpine-fastboot-return-{time.time_ns()}"
    receipt.mkdir(mode=0o700)
    report = {"state": "preflight", "partition_writes": False, "steps": []}

    def save():
        (receipt / "result.json").write_text(json.dumps(report, indent=2) + "\n")

    def step(name, command, payload=None, timeout=15):
        result = phone(command, payload, timeout)
        (receipt / f"{name}.stdout").write_bytes(result.stdout)
        (receipt / f"{name}.stderr").write_bytes(result.stderr)
        report["steps"].append({"name": name, "exit": result.returncode})
        save()
        if result.returncode:
            raise RuntimeError(name + " failed")
        return result.stdout.decode()

    try:
        helper = HELPER.read_bytes()
        if hashlib.sha256(helper).hexdigest() != HELPER_SHA or \
                not helper.startswith(b"\x7fELF"):
            raise RuntimeError("local reboot helper differs from tested artifact")
        status = json.loads(step("health", "/usr/local/bin/lynx-status --assert-ready"))
        if status["issues"] or status["battery"]["capacity_percent"] < 20 or \
                status["thermal"]["max_mC"] >= 55000:
            raise RuntimeError("Alpine or battery gate failed")
        report["boot_id"] = status["boot_id"]
        report["battery_percent"] = status["battery"]["capacity_percent"]
        step("identity", "set -eu; test \"$(sha256sum /dev/sdc39 | cut -c1-64)\" = "
             + V50_SHA + "; test ! -e " + REMOTE)
        step("stage", "set -eu; umask 077; cat > " + REMOTE + "; chmod 700 " +
             REMOTE + "; test \"$(sha256sum " + REMOTE +
             " | cut -c1-64)\" = " + HELPER_SHA, helper)
        report["state"] = "staged"
        save()
        # The tested helper issues exactly one Linux RESTART2("bootloader")
        # syscall. Sync persistent Alpine before the reset request.
        try:
            result = phone("set -eu; sync; exec " + REMOTE, timeout=8)
            report["request_exit"] = result.returncode
            (receipt / "request.stdout").write_bytes(result.stdout)
            (receipt / "request.stderr").write_bytes(result.stderr)
        except subprocess.TimeoutExpired as exc:
            report["request_exit"] = "ssh-disconnected-or-timeout"
            (receipt / "request.stdout").write_bytes(exc.stdout or b"")
            (receipt / "request.stderr").write_bytes(exc.stderr or b"")
        report["state"] = "reboot-requested"
        save()
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            if usb_probe()["fastboot_usb"]:
                query = subprocess.run(["sudo", "-n", str(FASTBOOT), "-s", SERIAL,
                                        "getvar", "product"],
                                       capture_output=True, text=True, timeout=8)
                if query.returncode == 0 and "product: k6983v1_64" in \
                        query.stdout + query.stderr:
                    report["state"] = "fastboot-verified"
                    break
            time.sleep(2)
        else:
            report["state"] = "fastboot-not-observed"
        save()
    except Exception as exc:
        report.update(state="failed", error=str(exc))
        save()
    print(json.dumps({"state": report["state"],
                      "receipt": str(receipt / "result.json"),
                      "error": report.get("error")}))
    if report["state"] != "fastboot-verified":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
