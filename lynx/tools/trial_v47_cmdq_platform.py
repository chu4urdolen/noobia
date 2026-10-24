"""Guarded RAM-only registration of the matching MT6983 CMDQ platform."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from lynx_wifi_v19_contact import ssh_command


ROOT = Path(__file__).resolve().parent.parent
MODULE = ROOT / "linux-port/artifacts/stock-cph2493-August-eu-ota/vendor-ramdisk-unpacked/lib/modules/cmdq-platform-mt6983.ko"
SHA = "3eabc1e9731637286264e7eb5a6d18485e668beb87b305797fcc43f10ef454ec"
BOOT_ID = "00841cdb-6658-44d6-9f47-4770b047cad5"
INIT_SHA = "ebc6bb746aaf710d915c47036f92ce0c4ed23a185dfb5349b90e654bab7ba4ae"
STAGE = "/run/lynx/display-test/cmdq-platform-mt6983.ko"


def main():
    data = MODULE.read_bytes()
    if hashlib.sha256(data).hexdigest() != SHA:
        raise SystemExit("stock module hash mismatch")
    vermagic = subprocess.run(["modinfo", "-F", "vermagic", str(MODULE)],
                             capture_output=True, text=True, check=True).stdout.strip()
    if not vermagic.startswith("5.10.149-android12-9-o-g311738fbb5a8 "):
        raise SystemExit("module ABI mismatch")
    os.umask(0o077)
    out = ROOT / "logs" / f"v47-cmdq-platform-{time.time_ns()}"
    out.mkdir(mode=0o700)
    result = {"state": "starting", "boot_id": BOOT_ID, "sha256": SHA,
              "vermagic": vermagic, "boot_partition_writes": False, "steps": []}

    def step(label, command, payload=None, port=2222, timeout=25):
        args = ssh_command("192.168.100.8", command)
        args[-2:-2] = ["-p", str(port)]
        run = subprocess.run(args, input=payload, capture_output=True, timeout=timeout)
        (out / f"{label}.stdout").write_bytes(run.stdout)
        (out / f"{label}.stderr").write_bytes(run.stderr)
        result["steps"].append({"name": label, "exit_code": run.returncode,
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
             'test ! -e /sys/module/cmdq_platform_mt6983; '
             'test ! -e /sys/module/oplus22823_tm_nt37705_fhd_dsi_cmd; '
             'grep -q "^mtk_cmdq_drv_ext " /proc/modules; '
             f'test ! -e {STAGE}; '
             'sample=$(cat /sys/bus/i2c/devices/7-0055/battery_snapshot); '
             'capacity=$(printf "%s\n" "$sample" | sed -n "s/^capacity_percent=//p"); '
             'temp=$(printf "%s\n" "$sample" | sed -n "s/^temperature_millidegrees_celsius=//p"); '
             'test "$capacity" -ge 70; test "$temp" -lt 35000')
        step("stage", f"mkdir -p /run/lynx/display-test; cat > {STAGE}", payload=data)
        step("stage_verify", f'test "$(sha256sum {STAGE} | cut -c1-64)" = "{SHA}"')
        step("insmod", f"/bin/busybox timeout 15 /sbin/insmod {STAGE}", timeout=25)
        step("after", "set -eu; "
             f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{BOOT_ID}"; '
             'grep -q "^cmdq_platform_mt6983 " /proc/modules; '
             '/usr/local/bin/lynx-status --assert-ready; '
             'printf "CMDQ="; grep "^cmdq_platform_mt6983 " /proc/modules; '
             'printf "RECENT="; dmesg | grep -i cmdq | tail -n 18 || :', timeout=35)
        result["state"] = "platform-loaded-host-healthy"
    except Exception as exc:
        result.update(state="failed-or-incomplete", error=str(exc))
    result["finished_ns"] = time.time_ns()
    path = out / "result.json"
    path.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"state": result["state"], "result": str(path)}))
    if result["state"] != "platform-loaded-host-healthy":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
