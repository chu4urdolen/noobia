"""Load one exact stock DVFSRC supplier in RAM, with V47 recovery guards."""

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
BOOT_ID = "00841cdb-6658-44d6-9f47-4770b047cad5"
INIT_SHA = "ebc6bb746aaf710d915c47036f92ce0c4ed23a185dfb5349b90e654bab7ba4ae"
MODULES = {
    "mtk-dvfsrc": {
        "sha": "f64bc73bbaa9acc5a9c6b8b5e83ee53ab21798acfdaa77819043e0c430a47913",
        "prereq": "grep -q '^mtk_scpsys ' /proc/modules",
        "verify": "test -L /sys/bus/platform/devices/1c00f000.dvfsrc/driver",
    },
    "mtk-dvfsrc-regulator": {
        "sha": "a49acf1bc974d7deae015befc2bb38df751e0050ae968d5e54ec0d52e44b1d6b",
        "prereq": "test -L /sys/bus/platform/devices/1c00f000.dvfsrc/driver; grep -q '^mtk_dvfsrc ' /proc/modules",
        "verify": "cat /sys/class/regulator/regulator.*/name | grep -qx dvfsrc-vcore",
    },
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("module", choices=MODULES)
    name = parser.parse_args().module
    spec = MODULES[name]
    module = MODULE_DIR / (name + ".ko")
    data = module.read_bytes()
    if hashlib.sha256(data).hexdigest() != spec["sha"]:
        raise SystemExit("stock module hash mismatch")
    vermagic = subprocess.run(["modinfo", "-F", "vermagic", str(module)],
                             capture_output=True, text=True, check=True).stdout.strip()
    if not vermagic.startswith("5.10.149-android12-9-o-g311738fbb5a8 "):
        raise SystemExit("module ABI mismatch")
    os.umask(0o077)
    out = ROOT / "logs" / f"v47-dvfsrc-supplier-{name}-{time.time_ns()}"
    out.mkdir(mode=0o700)
    report = {"module": name, "boot_id": BOOT_ID, "sha256": spec["sha"],
              "vermagic": vermagic, "boot_partition_writes": False,
              "steps": [], "state": "starting"}
    staged = "/run/lynx/display-test/" + name + ".ko"

    def step(label, command, payload=None, port=2222, timeout=25):
        args = ssh_command("192.168.100.8", command)
        args[-2:-2] = ["-p", str(port)]
        run = subprocess.run(args, input=payload, capture_output=True, timeout=timeout)
        (out / f"{label}.stdout").write_bytes(run.stdout)
        (out / f"{label}.stderr").write_bytes(run.stderr)
        report["steps"].append({"name": label, "exit_code": run.returncode,
                                "stdout_sha256": hashlib.sha256(run.stdout).hexdigest(),
                                "stderr_sha256": hashlib.sha256(run.stderr).hexdigest()})
        if run.returncode:
            raise RuntimeError(f"{label} failed; inspect receipt")

    try:
        step("rescue_identity", "set -eu; "
             f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{BOOT_ID}"; '
             f'test "$(sha256sum /init | cut -c1-64)" = "{INIT_SHA}"', port=22)
        step("preflight", "set -eu; "
             f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{BOOT_ID}"; '
             'test "$(uname -r)" = 5.10.149-android12-9-o-g311738fbb5a8; '
             '/usr/local/bin/lynx-status --assert-ready >/dev/null; '
             'test ! -e /sys/module/oplus22823_tm_nt37705_fhd_dsi_cmd; '
             f'test ! -e /sys/module/{name.replace("-", "_")}; '
             f'test ! -e {staged}; '
             f'{spec["prereq"]}; '
             'sample=$(cat /sys/bus/i2c/devices/7-0055/battery_snapshot); '
             'capacity=$(printf "%s\n" "$sample" | sed -n "s/^capacity_percent=//p"); '
             'temp=$(printf "%s\n" "$sample" | sed -n "s/^temperature_millidegrees_celsius=//p"); '
             'test "$capacity" -ge 70; test "$temp" -lt 35000')
        step("stage", f"mkdir -p /run/lynx/display-test; cat > {staged}", payload=data)
        step("stage_verify", f'test "$(sha256sum {staged} | cut -c1-64)" = "{spec["sha"]}"')
        step("insmod", f"/bin/busybox timeout 15 /sbin/insmod {staged}", timeout=25)
        step("after", "set -eu; "
             f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{BOOT_ID}"; '
             f'{spec["verify"]}; '
             '/usr/local/bin/lynx-status --assert-ready; '
             'printf "DVFSRC="; readlink /sys/bus/platform/devices/1c00f000.dvfsrc/driver; '
             'printf "REGULATORS="; cat /sys/class/regulator/regulator.*/name | grep dvfsrc || :; '
             'printf "RECENT="; dmesg | grep -Ei "dvfsrc|vcore" | tail -n 25 || :', timeout=35)
        report["state"] = "supplier-loaded-host-healthy"
    except Exception as exc:
        report.update(state="failed-or-incomplete", error=str(exc))
    report["finished_ns"] = time.time_ns()
    result = out / "result.json"
    result.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"state": report["state"], "result": str(result)}))
    if report["state"] != "supplier-loaded-host-healthy":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
