#!/usr/bin/env python3
"""Read-only 35-second verification of Lynx's already loaded RAM ISP module."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

from lynx_wifi_v19_contact import ssh_command

ROOT = Path(__file__).resolve().parent.parent
MODULE = ROOT / "linux-port/artifacts/camera-yuv-irq-rebuild-1793787441973056494/cam/mtk-cam-isp-stripped.ko"
MODULE_SHA = "0910503d465a9ea51b70a6b501fc7dead5f2eafd1f7d5a17845b1056eb5d9b3e"
BOOT_SHA = "c047455271828cf9bfa90984eea121d8ede8754f6297fc06f33f1e99fb23c75e"
REMOTE_MODULE = "/run/lynx/camera-isp-irq-trial/mtk-cam-isp.ko"


def main():
    out = ROOT / "logs" / f"camera-isp-patched-trial-{time.time_ns()}"
    out.mkdir(mode=0o700)
    report = {"schema": 1, "state": "verifying_loaded_module", "boot_partition_writes": False,
              "camera_capture_requested": False, "modules_unloaded": False,
              "candidate_sha256": MODULE_SHA, "read_only_loaded_module_check": True,
              "steps": []}

    def save():
        (out / "result.json").write_text(json.dumps(report, indent=2) + "\n")

    def step(name, command):
        argv = ssh_command("192.168.100.107", command)
        argv[-2:-2] = ["-p", "2222"]
        done = subprocess.run(argv, capture_output=True, timeout=12)
        (out / f"{name}.stdout").write_bytes(done.stdout)
        (out / f"{name}.stderr").write_bytes(done.stderr)
        report["steps"].append({"name": name, "exit": done.returncode, "at_ns": time.time_ns()})
        save()
        if done.returncode:
            raise RuntimeError(f"{name} failed")
        return done.stdout.decode(errors="replace").strip()

    try:
        if hashlib.sha256(MODULE.read_bytes()).hexdigest() != MODULE_SHA:
            raise RuntimeError("local ISP candidate changed")
        identity = step("identity", "cat /proc/sys/kernel/random/boot_id; "
                        "sha256sum /dev/sdc39 | cut -c1-64").splitlines()
        if len(identity) != 2 or identity[1] != BOOT_SHA:
            raise RuntimeError("unexpected V53 boot")
        report["boot_id"] = identity[0]
        if step("staged_module_hash", f"sha256sum {REMOTE_MODULE} | cut -c1-64") != MODULE_SHA:
            raise RuntimeError("staged ISP module differs")
        if "mtk_cam_isp " not in step("loaded_module", "cat /proc/modules"):
            raise RuntimeError("ISP module absent")
        deadline = time.monotonic() + 35
        sample = 0
        while True:
            snapshot = step(f"sample_{sample}", "grep cam_yuv_b /proc/interrupts; "
                            "echo __HEALTH__; /usr/local/bin/lynx-status --assert-ready; "
                            "echo __RCU__; dmesg | grep -E 'rcu_preempt detected stalls' | tail -3 || true")
            irq, rest = snapshot.split("__HEALTH__", 1)
            health_text, rcu = rest.split("__RCU__", 1)
            parts = irq.split()
            if (len(parts) < 9 or not parts[0].rstrip(":").isdigit()
                    or "cam_yuv_b" not in irq):
                raise RuntimeError("YUV-B IRQ line missing")
            count = sum(int(value) for value in parts[1:9])
            health = json.loads(health_text)
            if (count > 10000 or health["boot_id"] != identity[0]
                    or health["issues"] or rcu.strip()):
                raise RuntimeError("IRQ, boot, Alpine health, or RCU gate failed")
            report["last_irq_count"] = count
            report["last_battery_percent"] = health["battery"]["capacity_percent"]
            if time.monotonic() >= deadline:
                break
            sample += 1
            time.sleep(min(5, max(0, deadline - time.monotonic())))
        report["state"] = "stable_35_seconds_no_capture"
    except Exception as exc:
        report.update(state="failed", error=str(exc))
    save()
    print(json.dumps({"state": report["state"], "receipt": str(out / "result.json"),
                      "error": report.get("error")}))
    if report["state"] != "stable_35_seconds_no_capture":
        sys.exit(1)


if __name__ == "__main__":
    main()
