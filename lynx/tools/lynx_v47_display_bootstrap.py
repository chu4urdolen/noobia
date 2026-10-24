#!/usr/bin/env python3
"""Recreate Lynx's proven V47 DRM card registration in RAM.

Default mode checks the target and stock modules without changing Lynx.
Pass --apply only on a freshly booted V47 with sufficient battery. The tool
stops at the first failure, never retries panel binding, and writes no boot
partition or persistent startup file.
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
INIT_SHA = "ebc6bb746aaf710d915c47036f92ce0c4ed23a185dfb5349b90e654bab7ba4ae"
KERNEL = "5.10.149-android12-9-o-g311738fbb5a8"
IP = "192.168.100.8"
MODULES = (
    ("cmdq-platform-mt6983", "3eabc1e9731637286264e7eb5a6d18485e668beb87b305797fcc43f10ef454ec",
     "grep -q '^cmdq_platform_mt6983 ' /proc/modules"),
    ("tinysys-scmi", "6fa7f4469c3eaee17cb4d039dc30fe31e38bdd8c914925036ebe36861a8c04cf",
     "grep -q '^tinysys_scmi ' /proc/modules"),
    ("mtk-mminfra-debug", "7c40aa8abb29927e0bfef68484946f225b2dd5a8d983f411be166827a524eaff",
     "test -L /sys/bus/platform/devices/1e827000.mminfra-debug/driver"),
    ("mtk-dvfsrc", "f64bc73bbaa9acc5a9c6b8b5e83ee53ab21798acfdaa77819043e0c430a47913",
     "test -L /sys/bus/platform/devices/1c00f000.dvfsrc/driver"),
    ("mtk-dvfsrc-regulator", "a49acf1bc974d7deae015befc2bb38df751e0050ae968d5e54ec0d52e44b1d6b",
     "cat /sys/class/regulator/regulator.*/name | grep -qx dvfsrc-vcore"),
    ("pinctrl-mt6373", "c48f4fe779e3dd084d329a441f51d381df9b004c3d566520233215a1b92c6694",
     "test -L /sys/bus/platform/devices/mt6373-pinctrl/driver"),
    ("mtk-spmi-pmic-adc", "66a3e5426b200acf783413a09561e584cb89fd20244d9d8568d399431468e01c",
     "test -L /sys/bus/platform/devices/mt6373-auxadc/driver"),
    ("mtk_iommu", "f2f2d31ec2dcb769311dfab3621622a7deff7ba83d14c2f5137d94f38c44b332",
     "test \"$(ls /sys/class/iommu | wc -l)\" -ge 1"),
    ("mtk-mml-mt6983", "473c429e8b71aded1fe2f6f9128210e7fdd62df32f1d9cae234a92ac818578a5",
     "grep -q '^mtk_mml_mt6983 ' /proc/modules"),
    ("oplus22823_tm_nt37705_fhd_dsi_cmd", "498be900a01f21eba3116820d4fae965ee3796a953d30f66fb4aa72436334e98",
     "grep -q '^oplus22823_tm_nt37705_fhd_dsi_cmd ' /proc/modules"),
)


def module_bytes():
    values = []
    for name, digest, check in MODULES:
        path = MODULE_DIR / (name + ".ko")
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != digest:
            raise RuntimeError(f"{name}: stock module hash mismatch")
        vermagic = subprocess.run(["modinfo", "-F", "vermagic", str(path)],
                                 capture_output=True, text=True,
                                 check=True).stdout.strip()
        if not vermagic.startswith(KERNEL + " "):
            raise RuntimeError(f"{name}: module ABI mismatch")
        values.append((name, digest, check, data))
    return values


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true",
                        help="load verified modules and bind the panel once")
    args = parser.parse_args()
    modules = module_bytes()
    os.umask(0o077)
    out = ROOT / "logs" / f"v47-display-bootstrap-{time.time_ns()}"
    out.mkdir(mode=0o700)
    report = {"state": "starting", "apply": args.apply,
              "boot_partition_writes": False, "steps": []}

    def step(label, command, payload=None, port=2222, timeout=25):
        argv = ssh_command(IP, command)
        argv[-2:-2] = ["-p", str(port)]
        run = subprocess.run(argv, input=payload, capture_output=True,
                             timeout=timeout)
        (out / f"{label}.stdout").write_bytes(run.stdout)
        (out / f"{label}.stderr").write_bytes(run.stderr)
        report["steps"].append({"name": label, "exit_code": run.returncode,
                                "stdout_sha256": hashlib.sha256(run.stdout).hexdigest(),
                                "stderr_sha256": hashlib.sha256(run.stderr).hexdigest()})
        if run.returncode:
            raise RuntimeError(f"{label} failed; inspect saved streams")
        return run.stdout.decode(errors="replace").strip()

    try:
        identity = step("rescue_identity", "set -eu; "
                        "cat /proc/sys/kernel/random/boot_id; uname -r; "
                        "sha256sum /init | cut -c1-64", port=22).splitlines()
        if len(identity) != 3 or identity[1] != KERNEL or identity[2] != INIT_SHA:
            raise RuntimeError("target is not the pinned V47 kernel and rescue image")
        boot_id = identity[0]
        report["boot_id"] = boot_id
        status = step("alpine_health", "set -eu; "
                      f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{boot_id}"; '
                      "/usr/local/bin/lynx-status --assert-ready")
        health = json.loads(status)
        report["battery_percent"] = health["battery"]["capacity_percent"]
        report["battery_temperature_mC"] = health["battery"]["temperature_mC"]
        report["battery_current_mA_signed"] = health["battery"]["current_mA_signed"]
        report["thermal_max_mC"] = health["thermal"]["max_mC"]
        charger = step("charger_state", "set -eu; "
                       "supply=/sys/class/power_supply/11e01000.i2c:mt6375@34:chg; "
                       "cat \"$supply/online\"; cat \"$supply/status\"").splitlines()
        report["charger_online"] = charger[0] if charger else "unknown"
        report["charger_status"] = charger[1] if len(charger) > 1 else "unknown"
        state = step("display_state", "set -eu; "
                     'printf "CARD="; test -e /sys/class/drm/card0 && echo yes || echo no; '
                     'printf "PANEL="; test -e /sys/module/oplus22823_tm_nt37705_fhd_dsi_cmd && echo yes || echo no; '
                     'printf "DSI="; test -L /sys/bus/platform/devices/14017000.dsi/driver && echo yes || echo no; '
                     'printf "DT="; tr "\\000" "\\n" '
                     '</proc/device-tree/dsi@14017000/panel5@0/compatible | head -n 1')
        if "DT=oplus22823,tm,nt37705,cmd" not in state:
            raise RuntimeError("active device-tree panel is not the expected Tianma NT37705")
        mminfra = step("mminfra_dt", "set -eu; "
                        "node=/sys/firmware/devicetree/base/mminfra-debug@0x1e827000; "
                        "test -f \"$node/init-clk-on\"; "
                        "test \"$(od -An -tu4 -N4 \"$node/mminfra-bkrs\" | tr -d ' ')\" != 0; "
                        "tr '\\000' ' ' < \"$node/compatible\"")
        if "mediatek,mminfra-debug" not in mminfra:
            raise RuntimeError("active multimedia power-domain DT node is unexpected")
        if not args.apply:
            report["state"] = "checked-no-changes"
            print(f"V47 target checked: boot {boot_id}, battery "
                  f"{report['battery_percent']}%, {state.replace(chr(10), ' ')}")
        else:
            if (report["battery_percent"] < 45 or
                report["charger_online"] != "1" or
                report["charger_status"] not in ("Charging", "Full") or
                report["battery_temperature_mC"] >= 30000 or
                report["thermal_max_mC"] >= 45000):
                raise RuntimeError("battery must be at least 45%, charger online and charging, "
                                   "battery below 30°C, and sensors below 45°C")
            if "CARD=yes" in state or "PANEL=yes" in state or "DSI=yes" in state:
                raise RuntimeError("display was already probed on this boot; refusing a repeat")
            for name, digest, check, data in modules:
                target = "/run/lynx/display-test/" + name + ".ko"
                modname = name.replace("-", "_")
                step(f"{name}_preflight", "set -eu; "
                     f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{boot_id}"; '
                     f"test ! -e /sys/module/{modname}; test ! -e {target}; "
                     "/usr/local/bin/lynx-status --assert-ready >/dev/null")
                step(f"{name}_stage", f"mkdir -p /run/lynx/display-test; cat > {target}",
                     payload=data, timeout=40)
                step(f"{name}_verify", "set -eu; "
                     f'test "$(sha256sum {target} | cut -c1-64)" = "{digest}"')
                step(f"{name}_load", f"/bin/busybox timeout 15 /sbin/insmod {target}",
                     timeout=25)
                step(f"{name}_after", "set -eu; "
                     f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{boot_id}"; '
                     f"{check}; /usr/local/bin/lynx-status --assert-ready >/dev/null")
            step("dsi_bind_once", "set -eu; "
                 f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{boot_id}"; '
                 "test ! -L /sys/bus/platform/devices/14017000.dsi/driver; "
                 "/bin/busybox timeout 20 /bin/sh -c "
                 "'printf 14017000.dsi > /sys/bus/platform/drivers/mtk-dsi/bind'",
                 timeout=30)
            step("drm_ready", "set -eu; "
                 f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{boot_id}"; '
                 "test -c /dev/dri/card0; "
                 "test \"$(cat /sys/class/drm/card0-DSI-1/status)\" = connected; "
                 "/usr/local/bin/lynx-status --assert-ready")
            report["state"] = "drm-card-registered-host-healthy"
    except Exception as exc:
        report.update(state="failed-or-incomplete", error=str(exc))
    report["finished_ns"] = time.time_ns()
    path = out / "result.json"
    path.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"state": report["state"], "result": str(path)}))
    if report["state"] not in ("checked-no-changes", "drm-card-registered-host-healthy"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
