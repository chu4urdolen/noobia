#!/usr/bin/env python3
"""Install bounded fusion sensing on Lynx with service rollback."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

from lynx_wifi_v19_contact import ssh_command


ROOT = Path(__file__).resolve().parent.parent
FILES = (
    (ROOT / "tools/lynx_hf_sample.py", "/usr/local/bin/lynx-hf-sample",
     "/usr/local/bin/lynx-hf-sample.before-fusion-20261028"),
    (ROOT / "tools/lynx_noob_runtime.py", "/usr/local/bin/lynx-noobd",
     "/usr/local/bin/lynx-noobd.before-fusion-20261028"),
)
BOOT = "6168cd6288679a321a4d8bc41c7d3dde64a49d3cfe855b8e44542f3307fd5a59"


def ssh(command, data=None, timeout=20):
    args = ssh_command("192.168.100.107", command)
    args[-2:-2] = ["-p", "2222"]
    return subprocess.run(args, input=data, capture_output=True, timeout=timeout)


def main():
    receipt = ROOT / "logs" / f"v50-fusion-nrp-install-{time.time_ns()}"
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

    backups_ready = False
    try:
        if step("identity", "sha256sum /dev/sdc39 | cut -c1-64") != BOOT:
            raise RuntimeError("not verified V50")
        health = json.loads(step("health", "/usr/local/bin/lynx-status --assert-ready"))
        if health["battery"]["capacity_percent"] < 25 or \
           health["battery"]["temperature_mC"] >= 35000 or \
           health["thermal"]["max_mC"] >= 45000:
            raise RuntimeError("health guard failed")
        step("preflight", "set -eu; rc-service lynx-sensorhub status; "
             "rc-service lynx-noobd status; test -c /dev/hf_manager")
        for local, remote, backup in FILES:
            staged = "/run/" + local.name + ".fusion-candidate"
            data = local.read_bytes()
            digest = hashlib.sha256(data).hexdigest()
            step(local.stem + "_stage", f"cat > {staged}; chmod 700 {staged}; "
                 f'test "$(sha256sum {staged} | cut -c1-64)" = {digest}; '
                 f"/usr/bin/python3 -m py_compile {staged}", data)
        step("backup", "set -eu; " + "; ".join(f"cp -p {remote} {backup}"
                                                 for _, remote, backup in FILES))
        backups_ready = True
        step("install", "set -eu; " + "; ".join(
            f"cp /run/{local.name}.fusion-candidate {remote}; chmod 755 {remote}"
            for local, remote, _ in FILES) + "; rc-service lynx-noobd restart")
        step("verify", "set -eu; rc-service lynx-noobd status; "
             "/usr/local/bin/lynx-status --assert-ready >/dev/null")
        for attempt in range(5):
            result = subprocess.run([sys.executable, str(ROOT / "tools/lynx_noobctl.py"),
                                     "CALL", "FUSION_STATUS", "9"], capture_output=True,
                                    text=True, timeout=5)
            if result.returncode == 0 and "OK value=1" in result.stdout:
                break
            time.sleep(0.25)
        else:
            raise RuntimeError("fusion NRP status unavailable")
        report["fusion_status"] = result.stdout.strip()
        report["state"] = "installed"
    except Exception as exc:
        report.update(state="failed", error=str(exc))
        if backups_ready:
            rollback = ssh("set -eu; " + "; ".join(f"cp {backup} {remote}"
                            for _, remote, backup in FILES) + "; rc-service lynx-noobd restart")
            (receipt / "rollback.stdout").write_bytes(rollback.stdout)
            (receipt / "rollback.stderr").write_bytes(rollback.stderr)
            report["rollback_exit"] = rollback.returncode
    (receipt / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"state": report["state"], "receipt": str(receipt / "result.json"),
                      "status": report.get("fusion_status"), "error": report.get("error")}))
    if report["state"] != "installed":
        sys.exit(1)


if __name__ == "__main__":
    main()
