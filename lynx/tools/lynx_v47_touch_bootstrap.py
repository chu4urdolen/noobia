#!/usr/bin/env python3
"""Check or load the matching stock SPI touchscreen stack into V47 RAM.

No firmware update command, reboot, boot write, or persistent service change.
The touchscreen's own probe can talk to the controller; inspect its receipt.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from lynx_wifi_v19_contact import ssh_command


ROOT = Path(__file__).resolve().parent.parent
MODULE_DIR = ROOT / "linux-port/artifacts/stock-cph2493-August-eu-ota/vendor-ramdisk-unpacked/lib/modules"
KERNEL = "5.10.149-android12-9-o-g311738fbb5a8"
INIT_SHA = "ebc6bb746aaf710d915c47036f92ce0c4ed23a185dfb5349b90e654bab7ba4ae"
PANEL_MATCH = "oplus22823_tm_nt37705_fhd_dsi_cmd-synaptics-s3910"
MODULES = (
    ("olc", "2f08e1db185eed2ff9d688f1379f031de4fa6f521b27bd780478b13d0154fb3b"),
    ("oplus_bsp_fw_update", "0620cb21b581fc2f4b8a6433da4afedab2adae9f8c57b75c245d69d6dd8144aa"),
    ("oplus_bsp_tp_custom", "7bb8e255ad85abd8442e0c4bcd42c22c1d1fc88651f81c9907f3661f10d55a94"),
    ("spi-mt65xx", "65f2efa68b7929165c34b2754009412f0c1efd14fe98e45e0245c75665a6053d"),
    ("synaptics_tcm2", "2c759454da4c78d4b5b82815e9b71df1930c7c372af530673b6b61f85034a80a"),
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    os.umask(0o077)
    out = ROOT / "logs" / f"v47-touch-bootstrap-{time.time_ns()}"
    out.mkdir(mode=0o700)
    report = {"state": "starting", "apply": args.apply,
              "boot_partition_writes": False, "firmware_update_commands": False,
              "steps": []}

    def step(label, command, payload=None, port=2222, timeout=22):
        argv = ssh_command("192.168.100.8", command)
        argv[-2:-2] = ["-p", str(port)]
        try:
            run = subprocess.run(argv, input=payload, capture_output=True,
                                 timeout=timeout)
            stdout, stderr, code = run.stdout, run.stderr, run.returncode
        except subprocess.TimeoutExpired as exc:
            stdout, stderr, code = exc.stdout or b"", exc.stderr or b"", None
        (out / f"{label}.stdout").write_bytes(stdout)
        (out / f"{label}.stderr").write_bytes(stderr)
        report["steps"].append({"name": label, "exit_code": code})
        if code != 0:
            raise RuntimeError(f"{label} failed or timed out; inspect saved streams")
        return stdout.decode(errors="replace").strip()

    try:
        payloads = []
        for name, digest in MODULES:
            path = MODULE_DIR / (name + ".ko")
            data = path.read_bytes()
            if hashlib.sha256(data).hexdigest() != digest:
                raise RuntimeError(f"{name}: stock hash mismatch")
            vermagic = subprocess.run(["modinfo", "-F", "vermagic", str(path)],
                                     capture_output=True, text=True,
                                     check=True).stdout.strip()
            if not vermagic.startswith(KERNEL + " "):
                raise RuntimeError(f"{name}: kernel ABI mismatch")
            payloads.append((name, digest, data))
        lines = step("rescue_identity", "cat /proc/sys/kernel/random/boot_id; "
                     "uname -r; sha256sum /init | cut -c1-64", port=22).splitlines()
        if len(lines) != 3 or lines[1:] != [KERNEL, INIT_SHA]:
            raise RuntimeError("target is not the pinned V47 rescue and kernel")
        boot_id = lines[0]
        report["boot_id"] = boot_id
        status = json.loads(step("alpine_health", "/usr/local/bin/lynx-status --assert-ready"))
        if status["boot_id"] != boot_id:
            raise RuntimeError("Alpine and rescue boot IDs disagree")
        report["battery_percent"] = status["battery"]["capacity_percent"]
        report["battery_temperature_mC"] = status["battery"]["temperature_mC"]
        report["thermal_max_mC"] = status["thermal"]["max_mC"]
        charger = step("charger_state", "set -eu; "
                       "supply=/sys/class/power_supply/11e01000.i2c:mt6375@34:chg; "
                       "cat \"$supply/online\"; cat \"$supply/status\"").splitlines()
        report["charger_online"] = charger[0] if charger else "unknown"
        report["charger_status"] = charger[1] if len(charger) > 1 else "unknown"
        state = step("touch_state", "set -eu; "
                     f'grep -q "oplus_bsp_tp_custom.dsi_display0={PANEL_MATCH}" /proc/cmdline; '
                     "printf 'SPI='; tr '\\000' ' ' "
                     "</sys/firmware/devicetree/base/spi6@11016000/status; echo; "
                     "printf 'TOUCH='; tr '\\000' ' ' "
                     "</sys/firmware/devicetree/base/spi6@11016000/synaptics_tcm_hbp@0/compatible; echo; "
                     "for n in device_info mtk_disp_notify oplus_bsp_tp_notify; do "
                     "test -d /sys/module/$n || exit 1; done; "
                     "test ! -d /sys/module/synaptics_tcm2")
        if "SPI=okay" not in state or "TOUCH=synaptics,tcm-spi-hbp" not in state:
            raise RuntimeError("active touch DT node does not match stock module")
        if not args.apply:
            report["state"] = "checked-no-changes"
        else:
            if (status["battery"]["capacity_percent"] < 50 or
                report["charger_online"] != "0" or
                status["battery"]["temperature_mC"] >= 30000 or
                status["thermal"]["max_mC"] >= 45000):
                raise RuntimeError("battery or temperature outside touch trial guard")
            for name, digest, data in payloads:
                modname = name.replace("-", "_")
                target = "/run/lynx/touch-test/" + name + ".ko"
                step(name + "_preflight", "set -eu; "
                     f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{boot_id}"; '
                     f"test ! -e /sys/module/{modname}; "
                     "/usr/local/bin/lynx-status --assert-ready >/dev/null")
                step(name + "_stage", f"mkdir -p /run/lynx/touch-test; cat > {target}",
                     payload=data, timeout=40)
                step(name + "_verify", f'test "$(sha256sum {target} | cut -c1-64)" = "{digest}"')
                load = f"/bin/busybox timeout 15 /sbin/insmod {target}"
                if name == "oplus_bsp_tp_custom":
                    # insmod does not import a late module's /proc/cmdline option.
                    load += f" dsi_display0={PANEL_MATCH}"
                step(name + "_load", load,
                     timeout=22)
                step(name + "_after", "set -eu; "
                     f"grep -q '^{modname} ' /proc/modules; "
                     "/usr/local/bin/lynx-status --assert-ready >/dev/null")
            report["input_nodes"] = step("input_nodes", "set -eu; "
                "for d in /sys/class/input/input*; do test -e \"$d/name\" || continue; "
                "printf '%s ' \"$d\"; cat \"$d/name\"; done; "
                "for d in /dev/input/event*; do test -e \"$d\" && ls -l \"$d\"; done; true")
            report["state"] = "touch-modules-loaded-host-healthy"
    except Exception as exc:
        report.update(state="failed-or-incomplete", error=str(exc))
    finally:
        report["finished_ns"] = time.time_ns()
        path = out / "result.json"
        path.write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps({"state": report["state"], "result": str(path)}))
    if report["state"] not in ("checked-no-changes", "touch-modules-loaded-host-healthy"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
