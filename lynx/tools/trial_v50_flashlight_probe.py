#!/usr/bin/env python3
"""Probe Lynx's exact LM3642 module in RAM, without lighting the LED."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

from lynx_wifi_v19_contact import ssh_command


ROOT = Path(__file__).resolve().parent.parent
STOCK = ROOT / "linux-port/artifacts/stock-cph2493-August-eu-ota/wifi-reference/vendor-dlkm-unpacked/lib/modules"
MODULES = (
    ("mtk_battery_oc_throttling", "2285905a04532af8eaf2a04ad436eb14b4c8a7fc2bdbeaed3e5f647005b0cdf3"),
    ("flashlight", "58dbf6edb80115078739a3b008ef73a2bad734f9c4812a1f34b8e28ae36bb915"),
    ("lm3642_22823", "96dc429c39453dbd0ba469069655bfafc43e329cc3216d912bb080e87b7bef67"),
)
KERNEL = "5.10.149-android12-9-o-g311738fbb5a8"
BOOT = "6168cd6288679a321a4d8bc41c7d3dde64a49d3cfe855b8e44542f3307fd5a59"
STAGE = "/run/lynx/flashlight-probe"


def ssh(command, data=None, timeout=15):
    args = ssh_command("192.168.100.107", command)
    args[-2:-2] = ["-p", "2222"]
    return subprocess.run(args, input=data, capture_output=True, timeout=timeout)


def main():
    # The 2026-10-28 trial bound the chip, then flashlight.ko removal timed out
    # and Lynx disappeared from Wi-Fi. Keep the diagnostic code, but do not
    # repeat it until the removal failure has been understood and redesigned.
    sys.exit("paused: review logs/v50-flashlight-probe-1793224037686461488/ "
             "before any further flashlight trial")
    receipt = ROOT / "logs" / f"v50-flashlight-probe-{time.time_ns()}"
    receipt.mkdir(mode=0o700)
    report = {"state": "preflight", "boot_partition_writes": False,
              "led_actuation_requested": False, "persistent_phone_files": False,
              "steps": [], "loaded": [], "attempted": []}

    def save():
        (receipt / "result.json").write_text(json.dumps(report, indent=2) + "\n")

    def step(name, command, data=None, timeout=15):
        proc = ssh(command, data, timeout)
        (receipt / f"{name}.stdout").write_bytes(proc.stdout)
        (receipt / f"{name}.stderr").write_bytes(proc.stderr)
        report["steps"].append({"name": name, "exit": proc.returncode})
        save()
        if proc.returncode:
            raise RuntimeError(f"{name} failed; see receipt")
        return proc.stdout.decode(errors="replace").strip()

    stage_created = False
    try:
        identity = step("identity", "cat /proc/sys/kernel/random/boot_id; uname -r; "
                        "sha256sum /dev/sdc39 | cut -c1-64").splitlines()
        if len(identity) != 3 or identity[1:] != [KERNEL, BOOT]:
            raise RuntimeError("not verified V50")
        report["boot_id"] = identity[0]
        health = json.loads(step("health_before", "/usr/local/bin/lynx-status --assert-ready"))
        if health["boot_id"] != identity[0] or \
           health["battery"]["capacity_percent"] < 50 or \
           health["battery"]["temperature_mC"] >= 35000 or \
           health["thermal"]["max_mC"] >= 45000 or \
           health["root_free_mib"] < 400:
            raise RuntimeError("battery, thermal, or storage guard failed")
        step("preflight", "set -eu; test \"$(cat /sys/bus/i2c/devices/6-0063/name)\" = lm3642_22823; "
             "test ! -e /sys/bus/i2c/devices/6-0063/driver; "
             "grep -q '^mtk_pbm ' /proc/modules; rc-service lynx-wifi status; "
             "rc-service lynx-audio status; " +
             "; ".join(f"! grep -q '^{name} ' /proc/modules" for name, _ in MODULES) +
             f"; test ! -e {STAGE}")
        plan = []
        for name, digest in MODULES:
            path = STOCK / f"{name}.ko"
            data = path.read_bytes()
            if hashlib.sha256(data).hexdigest() != digest:
                raise RuntimeError(f"stock module checksum mismatch: {name}")
            magic = subprocess.run(["modinfo", "-F", "vermagic", str(path)],
                                   capture_output=True, text=True, check=True).stdout.strip()
            if not magic.startswith(KERNEL + " "):
                raise RuntimeError(f"kernel ABI mismatch: {name}")
            plan.append((name, digest, data))
        report["plan"] = [{"name": n, "sha256": h} for n, h, _ in plan]
        step("directory", f"mkdir -m 700 {STAGE}")
        stage_created = True
        for name, digest, data in plan:
            remote = f"{STAGE}/{name}.ko"
            step(name + "_stage", f"cat > {remote}", data, timeout=25)
            step(name + "_verify", f'test "$(sha256sum {remote} | cut -c1-64)" = {digest}')
            report["attempted"].append(name)
            save()
            step(name + "_load", f"/bin/busybox timeout 12 /sbin/insmod {remote}", timeout=18)
            report["loaded"].append(name)
            save()
            step(name + "_after", f"set -eu; grep -q '^{name} ' /proc/modules; "
                 "/usr/local/bin/lynx-status --assert-ready >/dev/null; "
                 "rc-service lynx-wifi status")
        binding = step("binding", "if test -L /sys/bus/i2c/devices/6-0063/driver; "
                       "then readlink /sys/bus/i2c/devices/6-0063/driver; else echo UNBOUND; fi; "
                       "find /dev -maxdepth 1 -name 'v4l-subdev*' -o -name 'flashlight'; "
                       "dmesg | grep -Ei 'lm3642_22823|flashlight_core|flashlight' | tail -40")
        report["bound"] = "UNBOUND" not in binding.splitlines()[:1]
        report["state"] = "probe-complete-awaiting-cleanup"
    except Exception as exc:
        report.update(state="failed-or-incomplete", error=str(exc))
    finally:
        cleanup = []
        for name in reversed(report["attempted"]):
            try:
                proc = ssh(f"if grep -q '^{name} ' /proc/modules; then "
                           f"/bin/busybox timeout 8 /sbin/rmmod {name}; fi", timeout=12)
            except (subprocess.TimeoutExpired, OSError) as exc:
                cleanup.append({"name": name, "exit": str(exc)})
                break
            (receipt / f"cleanup-{name}.stdout").write_bytes(proc.stdout)
            (receipt / f"cleanup-{name}.stderr").write_bytes(proc.stderr)
            cleanup.append({"name": name, "exit": proc.returncode})
        report["cleanup"] = cleanup
        if stage_created and not any(c["exit"] for c in cleanup):
            proc = ssh(f"rm -rf {STAGE}")
            report["stage_cleanup_exit"] = proc.returncode
        post = "set -e; /usr/local/bin/lynx-status --assert-ready"
        if stage_created:
            if report["attempted"]:
                post += "; for m in " + " ".join(report["attempted"]) + "; do " \
                        "if grep -q \"^$m \" /proc/modules; then echo MODULE_REMAINS:$m; fi; done"
            post += "; if test -L /sys/bus/i2c/devices/6-0063/driver; " \
                    "then echo DRIVER_REMAINS; fi"
        try:
            proc = ssh(post, timeout=15)
            (receipt / "post_cleanup.stdout").write_bytes(proc.stdout)
            (receipt / "post_cleanup.stderr").write_bytes(proc.stderr)
            report["post_cleanup_exit"] = proc.returncode
            remains = b"REMAINS" in proc.stdout
        except (subprocess.TimeoutExpired, OSError) as exc:
            report["post_cleanup_exit"] = str(exc)
            remains = True
        report["cleanup_incomplete"] = (any(c["exit"] for c in cleanup) or
                                        report["post_cleanup_exit"] != 0 or remains)
        if report["cleanup_incomplete"]:
            report["state"] = "cleanup-incomplete"
        elif report["state"] == "probe-complete-awaiting-cleanup":
            report["state"] = "bound-cleaned" if report.get("bound") else "unbound-cleaned"
        save()
    print(json.dumps({"state": report["state"], "receipt": str(receipt / "result.json"),
                      "bound": report.get("bound"), "error": report.get("error")}))
    if report["state"] != "bound-cleaned":
        sys.exit(1)


if __name__ == "__main__":
    main()
