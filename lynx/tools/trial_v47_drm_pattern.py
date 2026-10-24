"""Bounded 60 Hz DRM SMPTE pattern trial on a healthy V47 boot."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from lynx_wifi_v19_contact import ssh_command


ROOT = Path(__file__).resolve().parent.parent
BOOT_ID = "00841cdb-6658-44d6-9f47-4770b047cad5"
INIT_SHA = "ebc6bb746aaf710d915c47036f92ce0c4ed23a185dfb5349b90e654bab7ba4ae"


def main():
    os.umask(0o077)
    out = ROOT / "logs" / f"v47-drm-pattern-{time.time_ns()}"
    out.mkdir(mode=0o700)
    result = {"state": "starting", "boot_id": BOOT_ID,
              "boot_partition_writes": False, "steps": []}

    def step(label, command, port=2222, timeout=25, allow_nonzero=False):
        args = ssh_command("192.168.100.8", command)
        args[-2:-2] = ["-p", str(port)]
        run = subprocess.run(args, capture_output=True, timeout=timeout)
        (out / f"{label}.stdout").write_bytes(run.stdout)
        (out / f"{label}.stderr").write_bytes(run.stderr)
        result["steps"].append({"name": label, "exit_code": run.returncode,
                                "stdout_sha256": hashlib.sha256(run.stdout).hexdigest(),
                                "stderr_sha256": hashlib.sha256(run.stderr).hexdigest()})
        if run.returncode and not allow_nonzero:
            raise RuntimeError(f"{label} failed; inspect receipt")
        return run.stdout.decode(errors="replace")

    try:
        step("rescue_identity", "set -eu; "
             f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{BOOT_ID}"; '
             f'test "$(sha256sum /init | cut -c1-64)" = "{INIT_SHA}"', port=22)
        step("preflight", "set -eu; "
             f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{BOOT_ID}"; '
             '/usr/local/bin/lynx-status --assert-ready >/dev/null; '
             'test -c /dev/dri/card0; '
             'test "$(cat /sys/class/drm/card0-DSI-1/status)" = connected; '
             'test -L /sys/bus/platform/devices/14017000.dsi/driver; '
             'grep -q "^cmdq_platform_mt6983 " /proc/modules; '
             'sample=$(cat /sys/bus/i2c/devices/7-0055/battery_snapshot); '
             'capacity=$(printf "%s\n" "$sample" | sed -n "s/^capacity_percent=//p"); '
             'temp=$(printf "%s\n" "$sample" | sed -n "s/^temperature_millidegrees_celsius=//p"); '
             'test "$capacity" -ge 70; test "$temp" -lt 35000')
        step("before", "modetest -M mediatek -c -p")
        # The pipe keeps modetest running for eight seconds if it waits for
        # input. The outer timeout bounds it even if the driver stalls.
        step("pattern", "/bin/busybox timeout 15 /bin/sh -c "
             "'sleep 8 | modetest -M mediatek -s 32@70:1240x2772-60@XR24 -F smpte'",
             timeout=23, allow_nonzero=True)
        step("after", "set -eu; "
             f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{BOOT_ID}"; '
             '/usr/local/bin/lynx-status --assert-ready; '
             'printf "CONNECTOR="; cat /sys/class/drm/card0-DSI-1/status; '
             'printf "RECENT="; dmesg | grep -Ei "drm|dsi|cmdq|panel|error" | tail -n 35 || :',
             timeout=35)
        result["state"] = "trial-completed-host-healthy"
    except Exception as exc:
        result.update(state="failed-or-incomplete", error=str(exc))
    result["finished_ns"] = time.time_ns()
    path = out / "result.json"
    path.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"state": result["state"], "result": str(path)}))
    if result["state"] != "trial-completed-host-healthy":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
