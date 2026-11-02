#!/usr/bin/env python3
"""Stage exact flashlight modules and a disabled OpenRC service on Lynx."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from lynx_wifi_v19_contact import ssh_command

ROOT = Path(__file__).resolve().parent.parent
STOCK = ROOT / "linux-port/artifacts/stock-cph2493-August-eu-ota/wifi-reference/vendor-dlkm-unpacked/lib/modules"
MODULES = {
    "mtk_battery_oc_throttling": "2285905a04532af8eaf2a04ad436eb14b4c8a7fc2bdbeaed3e5f647005b0cdf3",
    "flashlight": "58dbf6edb80115078739a3b008ef73a2bad734f9c4812a1f34b8e28ae36bb915",
    "lm3642_22823": "96dc429c39453dbd0ba469069655bfafc43e329cc3216d912bb080e87b7bef67",
}
FILES = {
    ROOT / "tools/lynx_flashlight_bootstrap.sh": "/usr/local/bin/lynx-flashlight-bootstrap",
    ROOT / "tools/openrc-lynx-flashlight": "/etc/init.d/lynx-flashlight",
}
KERNEL = "5.10.149-android12-9-o-g311738fbb5a8"


def main():
    os.umask(0o077)
    out = ROOT / "logs" / f"flashlight-service-stage-{time.time_ns()}"
    out.mkdir(mode=0o700)
    report = {"state": "starting", "modules_loaded": False,
              "service_started": False, "service_enabled": False,
              "boot_partition_writes": False, "steps": []}

    def step(name, command, data=None, timeout=25):
        argv = ssh_command("192.168.100.107", command)
        argv[-2:-2] = ["-p", "2222"]
        result = subprocess.run(argv, input=data, capture_output=True, timeout=timeout)
        (out / (name + ".stdout")).write_bytes(result.stdout)
        (out / (name + ".stderr")).write_bytes(result.stderr)
        report["steps"].append({"name": name, "exit": result.returncode})
        if result.returncode:
            raise RuntimeError(f"{name} failed; see receipt")
        return result.stdout.decode(errors="replace").strip()

    try:
        identity = step("identity", "uname -r; cat /proc/sys/kernel/random/boot_id").splitlines()
        if len(identity) != 2 or identity[0] != KERNEL:
            raise RuntimeError("unexpected kernel")
        report["boot_id"] = identity[1]
        health = json.loads(step("health", "/usr/local/bin/lynx-status --assert-ready"))
        if health["boot_id"] != identity[1] or health["issues"]:
            raise RuntimeError("health gate failed")
        step("absent", "set -eu; test ! -e /etc/init.d/lynx-flashlight; "
             "test ! -e /usr/local/bin/lynx-flashlight-bootstrap; "
             "test ! -e /usr/local/lib/lynx/flashlight; "
             "test ! -e /etc/runlevels/default/lynx-flashlight; " +
             "; ".join(f"! grep -q '^{name} ' /proc/modules" for name in MODULES))
        step("directory", "mkdir -p /usr/local/lib/lynx/flashlight; "
             "chmod 700 /usr/local/lib/lynx/flashlight")
        for name, expected in MODULES.items():
            data = (STOCK / (name + ".ko")).read_bytes()
            if hashlib.sha256(data).hexdigest() != expected:
                raise RuntimeError("stock module changed: " + name)
            target = "/usr/local/lib/lynx/flashlight/" + name + ".ko"
            step("module_" + name, f"cat > {target}.new", data, timeout=40)
            step("module_install_" + name,
                 f"test \"$(sha256sum {target}.new | cut -c1-64)\" = {expected}; "
                 f"chmod 600 {target}.new; mv {target}.new {target}")
        for source, target in FILES.items():
            data = source.read_bytes()
            digest = hashlib.sha256(data).hexdigest()
            step("file_" + source.name, f"cat > {target}.new", data)
            step("file_install_" + source.name,
                 f"test \"$(sha256sum {target}.new | cut -c1-64)\" = {digest}; "
                 f"chmod 755 {target}.new; mv {target}.new {target}")
        step("syntax", "sh -n /usr/local/bin/lynx-flashlight-bootstrap; "
             "sh -n /etc/init.d/lynx-flashlight")
        step("disabled", "set -eu; test ! -e /etc/runlevels/default/lynx-flashlight; "
             "test ! -L /sys/bus/i2c/devices/6-0063/driver; "
             "test ! -e /dev/flashlight")
        post = json.loads(step("post_health", "/usr/local/bin/lynx-status --assert-ready"))
        if post["boot_id"] != identity[1] or post["issues"]:
            raise RuntimeError("post-stage health changed")
        report["state"] = "staged-disabled-no-module-load"
    except Exception as exc:
        report.update(state="failed-or-incomplete", error=str(exc))
    (out / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"state": report["state"], "receipt": str(out / "result.json"),
                      "error": report.get("error")}))
    if report["state"] != "staged-disabled-no-module-load":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
