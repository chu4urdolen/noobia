#!/usr/bin/env python3
"""Apply Lynx's existing touch panel match string and retry one RAM-only probe."""

import json
import os
from pathlib import Path
import subprocess
import time

from lynx_wifi_v19_contact import ssh_command


ROOT = Path(__file__).resolve().parent.parent
BOOT_ID = "897cad51-2ae4-479a-98bc-9ab8a052b9a9"
MATCH = "oplus22823_tm_nt37705_fhd_dsi_cmd-synaptics-s3910"
MODULE = "/run/lynx/touch-test/synaptics_tcm2.ko"
MODULE_SHA = "2c759454da4c78d4b5b82815e9b71df1930c7c372af530673b6b61f85034a80a"


def main():
    os.umask(0o077)
    out = ROOT / "logs" / f"v47-touch-match-{time.time_ns()}"
    out.mkdir(mode=0o700)
    report = {"state": "starting", "boot_id": BOOT_ID,
              "boot_partition_writes": False, "firmware_update_commands": False,
              "steps": []}

    def step(label, command, timeout=25):
        argv = ssh_command("192.168.100.8", command)
        argv[-2:-2] = ["-p", "2222"]
        try:
            run = subprocess.run(argv, capture_output=True, timeout=timeout)
            stdout, stderr, code = run.stdout, run.stderr, run.returncode
        except subprocess.TimeoutExpired as exc:
            stdout, stderr, code = exc.stdout or b"", exc.stderr or b"", None
        (out / f"{label}.stdout").write_bytes(stdout)
        (out / f"{label}.stderr").write_bytes(stderr)
        report["steps"].append({"name": label, "exit_code": code})
        if code != 0:
            raise RuntimeError(f"{label} failed or timed out; inspect receipt")
        return stdout.decode(errors="replace").strip()

    try:
        pre = step("preflight", "set -eu; "
            f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{BOOT_ID}"; '
            f'grep -q "oplus_bsp_tp_custom.dsi_display0={MATCH}" /proc/cmdline; '
            "test -z \"$(cat /sys/module/oplus_bsp_tp_custom/parameters/dsi_display0)\"; "
            f'test "$(sha256sum {MODULE} | cut -c1-64)" = "{MODULE_SHA}"; '
            "grep -q '^synaptics_tcm2 ' /proc/modules; "
            "test ! -e /dev/input/event0; "
            "/usr/local/bin/lynx-status --assert-ready")
        health = json.loads(pre)
        charger = step("charger_state", "set -eu; "
                       "supply=/sys/class/power_supply/11e01000.i2c:mt6375@34:chg; "
                       "cat \"$supply/online\"; cat \"$supply/status\"").splitlines()
        if health["battery"]["capacity_percent"] < 50 or \
           len(charger) != 2 or charger[0] != "0" or \
           health["battery"]["temperature_mC"] >= 30000 or \
           health["thermal"]["max_mC"] >= 45000:
            raise RuntimeError("battery or temperature outside touch guard")
        # The initial driver's match failed before it registered a SPI probe.
        step("unload_unmatched", "set -eu; /sbin/rmmod synaptics_tcm2; "
             "test ! -e /sys/module/synaptics_tcm2")
        step("set_panel_match", "set -eu; "
             f"printf '%s' '{MATCH}' > /sys/module/oplus_bsp_tp_custom/parameters/dsi_display0; "
             f'test "$(cat /sys/module/oplus_bsp_tp_custom/parameters/dsi_display0)" = "{MATCH}"')
        step("load_matched", f"/bin/busybox timeout 25 /sbin/insmod {MODULE}",
             timeout=33)
        report["input_nodes"] = step("input_nodes", "set -eu; "
             "grep -q '^synaptics_tcm2 ' /proc/modules; "
             "for d in /sys/class/input/input*; do test -e \"$d/name\" || continue; "
             "printf '%s ' \"$d\"; cat \"$d/name\"; done; "
             "for d in /dev/input/event*; do test -e \"$d\" && ls -l \"$d\"; done; true; "
             "/usr/local/bin/lynx-status --assert-ready")
        report["state"] = "matched-probe-completed-host-healthy"
    except Exception as exc:
        report.update(state="failed-or-incomplete", error=str(exc))
    finally:
        report["finished_ns"] = time.time_ns()
        path = out / "result.json"
        path.write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps({"state": report["state"], "result": str(path)}))
    if report["state"] != "matched-probe-completed-host-healthy":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
