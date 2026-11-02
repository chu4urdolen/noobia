#!/usr/bin/env python3
"""Publish verified camera sensor binding in Lynx local and NRP status."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from lynx_wifi_v19_contact import ssh_command

ROOT = Path(__file__).resolve().parent.parent
FILES = {
    ROOT / "tools/lynx_noob_runtime.py": "/usr/local/bin/lynx-noobd",
    ROOT / "tools/lynx_hardware.py": "/usr/local/bin/lynx_hardware.py",
}
OLD = {
    "/usr/local/bin/lynx-noobd": "b8953e69aacd86db18f2f30a8ff88955f76b8d8136693a158824d173560f09f4",
    "/usr/local/bin/lynx_hardware.py": "538164c278d29488d16a40527231eadd0d89f7a2c3a5ca432319789bd413090b",
}
STAGE = "/run/lynx/camera-media-correction"


def main():
    os.umask(0o077)
    out = ROOT / "logs" / f"camera-inventory-noob-{time.time_ns()}"
    out.mkdir(mode=0o700)
    report = {"state": "starting", "boot_partition_writes": False,
              "modules_loaded": False, "steps": []}

    def step(name, command, data=None, timeout=25):
        argv = ssh_command("192.168.100.107", command)
        argv[-2:-2] = ["-p", "2222"]
        run = subprocess.run(argv, input=data, capture_output=True, timeout=timeout)
        (out / (name + ".stdout")).write_bytes(run.stdout)
        (out / (name + ".stderr")).write_bytes(run.stderr)
        report["steps"].append({"name": name, "exit": run.returncode})
        if run.returncode:
            raise RuntimeError(f"{name} failed; see receipt")
        return run.stdout.decode(errors="replace").strip()

    installed = False
    try:
        health = json.loads(step("health_before", "/usr/local/bin/lynx-status --assert-ready"))
        if health["issues"] or health["battery"]["capacity_percent"] < 50:
            raise RuntimeError("health gate failed")
        report["boot_id"] = health["boot_id"]
        for target, expected in OLD.items():
            if step("old_" + Path(target).name,
                    f"sha256sum {target} | cut -c1-64") != expected:
                raise RuntimeError("live service changed: " + target)
        step("directory", f"mkdir -m 700 {STAGE}")
        for source in FILES:
            data = source.read_bytes()
            digest = hashlib.sha256(data).hexdigest()
            step("stage_" + source.name, f"cat > {STAGE}/{source.name}", data)
            if step("hash_" + source.name,
                    f"sha256sum {STAGE}/{source.name} | cut -c1-64") != digest:
                raise RuntimeError("transfer checksum mismatch: " + source.name)
        step("syntax", f"python3 -m py_compile {STAGE}/lynx_noob_runtime.py "
             f"{STAGE}/lynx_hardware.py; "
             f"PYTHONPATH={STAGE} python3 {STAGE}/lynx_hardware.py status camera >/dev/null")
        step("backup", "cp -p /usr/local/bin/lynx-noobd "
             "/usr/local/bin/lynx-noobd.before-camera-media-correction; "
             "cp -p /usr/local/bin/lynx_hardware.py "
             "/usr/local/bin/lynx_hardware.py.before-camera-media-correction")
        installed = True
        for source, target in FILES.items():
            step("install_" + source.name,
                 f"cp {STAGE}/{source.name} {target}.new; chmod 755 {target}.new; "
                 f"mv {target}.new {target}")
        step("restart", "rc-service lynx-noobd restart", timeout=45)
        inventory = json.loads(step("inventory", "/usr/local/bin/lynx-hardware status camera"))
        report["inventory"] = inventory
        if (inventory["evidence"]["sensor_count"] != 4 or inventory["validated"] or
                inventory["interface_ready"] or
                inventory["evidence"]["processing_video_count"] < 1):
            raise RuntimeError("camera inventory not as expected")
        response = subprocess.run(["python3", str(ROOT / "tools/lynx_noobctl.py"),
                                   "CALL", "CAMERA_STATUS"],
                                  capture_output=True, text=True, timeout=12)
        report["nrp"] = response.stdout.strip()
        if (response.returncode or "sensors_bound=4" not in response.stdout or
                "interface_ready=0" not in response.stdout):
            raise RuntimeError("remote camera status incorrect")
        after = json.loads(step("health_after", "/usr/local/bin/lynx-status --assert-ready"))
        if after["boot_id"] != report["boot_id"] or after["issues"]:
            raise RuntimeError("post-install health changed")
        report["state"] = "installed-and-verified"
    except Exception as exc:
        report.update(state="failed", error=str(exc))
        if installed:
            try:
                step("rollback", "cp -p /usr/local/bin/lynx-noobd.before-camera-media-correction "
                     "/usr/local/bin/lynx-noobd; "
                     "cp -p /usr/local/bin/lynx_hardware.py.before-camera-media-correction "
                     "/usr/local/bin/lynx_hardware.py; rc-service lynx-noobd restart", timeout=45)
                report["state"] = "rolled-back"
            except Exception as rollback_exc:
                report["rollback_error"] = str(rollback_exc)
    (out / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"state": report["state"], "receipt": str(out / "result.json"),
                      "error": report.get("error")}))
    if report["state"] != "installed-and-verified":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
