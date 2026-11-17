#!/usr/bin/env python3
"""Install Lynx NRP touch reader with a verified service rollback."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

from lynx_wifi_v19_contact import ssh_command


ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "tools/lynx_noob_runtime.py"
BOOT = "6168cd6288679a321a4d8bc41c7d3dde64a49d3cfe855b8e44542f3307fd5a59"
KERNEL = "5.10.149-android12-9-o-g311738fbb5a8"


def ssh(command, data=None, timeout=20):
    args = ssh_command("192.168.100.107", command)
    args[-2:-2] = ["-p", "2222"]
    return subprocess.run(args, input=data, capture_output=True, timeout=timeout)


def main():
    receipt = ROOT / "logs" / f"v50-touch-nrp-install-{time.time_ns()}"
    receipt.mkdir(mode=0o700)
    report = {"state": "preflight", "boot_partition_writes": False, "steps": []}

    def step(name, command, data=None):
        proc = ssh(command, data)
        (receipt / f"{name}.stdout").write_bytes(proc.stdout)
        (receipt / f"{name}.stderr").write_bytes(proc.stderr)
        report["steps"].append({"name": name, "exit": proc.returncode})
        if proc.returncode:
            raise RuntimeError(f"{name} failed")
        return proc.stdout.decode(errors="replace").strip()

    staged = "/tmp/lynx-noobd-touch-candidate"
    backup = "/usr/local/bin/lynx-noobd.before-touch-pixels-20261028"
    digest = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    installed = False
    try:
        identity = step("identity", "uname -r; sha256sum /dev/sdc39 | cut -c1-64").splitlines()
        if identity != [KERNEL, BOOT]:
            raise RuntimeError("not verified V50")
        status = json.loads(step("health", "/usr/local/bin/lynx-status --assert-ready"))
        battery = status["battery"]
        if battery["capacity_percent"] < 25 or battery["temperature_mC"] >= 35000 or \
           status["thermal"]["max_mC"] >= 45000:
            raise RuntimeError("health guard failed")
        step("touch", "set -eu; test -c /dev/input/event0; "
             "test \"$(cat /sys/class/input/input0/name)\" = touchpanel; "
             "rc-service lynx-noobd status; test -S /run/lynx/media.sock")
        step("stage", f"cat > {staged}; chmod 700 {staged}; "
             f'test "$(sha256sum {staged} | cut -c1-64)" = {digest}', SOURCE.read_bytes())
        step("candidate", f"/usr/bin/python3 -m py_compile {staged}; "
             f"/usr/bin/python3 -c 'import importlib.machinery; "
             f"m=importlib.machinery.SourceFileLoader(\"candidate\",\"{staged}\").load_module(); "
             "t=m.TouchInput(); t.open_verified(); assert t.fd is not None; t.close()'")
        step("backup", f"cp -p /usr/local/bin/lynx-noobd {backup}")
        installed = True
        step("install", f"cp {staged} /usr/local/bin/lynx-noobd; "
             "chmod 755 /usr/local/bin/lynx-noobd; "
             "rc-service lynx-noobd restart")
        step("verify", "set -eu; rc-service lynx-noobd status; "
             "/usr/local/bin/lynx-status --assert-ready >/dev/null; "
             "test -c /dev/input/event0")
        report["state"] = "installed"
    except Exception as exc:
        report.update(state="failed", error=str(exc))
        if installed:
            recovery = ssh(f"cp {backup} /usr/local/bin/lynx-noobd; "
                           "rc-service lynx-noobd restart")
            (receipt / "rollback.stdout").write_bytes(recovery.stdout)
            (receipt / "rollback.stderr").write_bytes(recovery.stderr)
            report["rollback_exit"] = recovery.returncode
    (receipt / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"state": report["state"], "receipt": str(receipt / "result.json"),
                      "error": report.get("error")}))
    if report["state"] != "installed":
        sys.exit(1)


if __name__ == "__main__":
    main()
