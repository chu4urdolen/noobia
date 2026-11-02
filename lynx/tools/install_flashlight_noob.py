#!/usr/bin/env python3
"""Install Lynx's bounded flashlight local and NRP/1 tools with rollback."""

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
    ROOT / "tools/lynx_flashlight_pulse.py": "/usr/local/bin/lynx-flashlight-pulse",
    ROOT / "tools/local_calls/lynx_flashlight_pulse.sh": "/usr/local/share/lynx-tools/calls/lynx_flashlight_pulse.sh",
    ROOT / "tools/local_calls/lynx_flashlight_pulse.json": "/usr/local/share/lynx-tools/calls/lynx_flashlight_pulse.json",
    ROOT / "tools/local_calls/lynx_flashlight_stop.sh": "/usr/local/share/lynx-tools/calls/lynx_flashlight_stop.sh",
    ROOT / "tools/local_calls/lynx_flashlight_stop.json": "/usr/local/share/lynx-tools/calls/lynx_flashlight_stop.json",
}
OLD_RUNTIME = "b8953e69aacd86db18f2f30a8ff88955f76b8d8136693a158824d173560f09f4"
OLD_PULSE = "65b2180364b8ff3f518b7fde3b7c34c48de4559afb89021b5a9ff06b0f1759f9"
STAGE = "/run/lynx/flashlight-stop-install"


def main():
    os.umask(0o077)
    out = ROOT / "logs" / f"flashlight-noob-{time.time_ns()}"
    out.mkdir(mode=0o700)
    report = {"state": "starting", "boot_partition_writes": False,
              "modules_unloaded": False, "steps": []}

    def step(name, command, data=None, timeout=25):
        args = ssh_command("192.168.100.107", command)
        args[-2:-2] = ["-p", "2222"]
        result = subprocess.run(args, input=data, capture_output=True, timeout=timeout)
        (out / (name + ".stdout")).write_bytes(result.stdout)
        (out / (name + ".stderr")).write_bytes(result.stderr)
        report["steps"].append({"name": name, "exit": result.returncode})
        if result.returncode:
            raise RuntimeError(f"{name} failed; see receipt")
        return result.stdout.decode(errors="replace").strip()

    installed = False
    backup_runtime = "/usr/local/bin/lynx-noobd.before-flashlight-stop"
    backup_pulse = "/usr/local/bin/lynx-flashlight-pulse.before-stop"
    try:
        health = json.loads(step("health", "/usr/local/bin/lynx-status --assert-ready"))
        if health["issues"] or health["battery"]["capacity_percent"] < 25:
            raise RuntimeError("health gate failed")
        report["boot_id"] = health["boot_id"]
        if step("old_runtime", "sha256sum /usr/local/bin/lynx-noobd | cut -c1-64") != OLD_RUNTIME:
            raise RuntimeError("runtime changed since review")
        if step("old_pulse", "sha256sum /usr/local/bin/lynx-flashlight-pulse | cut -c1-64") != OLD_PULSE:
            raise RuntimeError("pulse tool changed since trial")
        step("ready", "set -eu; rc-service lynx-noobd status; "
             "test ! -e " + backup_runtime)
        step("directory", f"mkdir -m 700 {STAGE}")
        for source, target in FILES.items():
            data = source.read_bytes()
            digest = hashlib.sha256(data).hexdigest()
            temp = STAGE + "/" + source.name
            step("stage_" + source.name, f"cat > {temp}", data)
            if step("hash_" + source.name, f"sha256sum {temp} | cut -c1-64") != digest:
                raise RuntimeError("stage hash mismatch: " + source.name)
        step("syntax", f"python3 -m py_compile {STAGE}/lynx_noob_runtime.py "
             f"{STAGE}/lynx_flashlight_pulse.py; "
             f"PYTHONPATH={STAGE}:/usr/local/bin python3 -c 'from lynx_noob_runtime import Runtime; "
             "r=Runtime(); assert \"FLASH_PULSE\" in r.dispatch(\"NRP/1 1 CAPS\")'")
        step("backup", f"cp -p /usr/local/bin/lynx-noobd {backup_runtime}; "
             f"cp -p /usr/local/bin/lynx-flashlight-pulse {backup_pulse}")
        installed = True
        for source, target in FILES.items():
            mode = "644" if source.suffix == ".json" else "755"
            step("install_" + source.name,
                 f"cp {STAGE}/{source.name} {target}.new; chmod {mode} {target}.new; "
                 f"mv {target}.new {target}")
        step("restart", "rc-service lynx-noobd restart", timeout=45)
        step("service", "rc-service lynx-noobd status")
        response = subprocess.run(["python3", str(ROOT / "tools/lynx_noobctl.py"), "CAPS"],
                                  capture_output=True, text=True, timeout=12)
        report["caps"] = response.stdout.strip()
        if (response.returncode or "FLASH_PULSE" not in response.stdout or
                "FLASH_STOP" not in response.stdout):
            raise RuntimeError("remote CAPS lacks flashlight controls")
        post = json.loads(step("post_health", "/usr/local/bin/lynx-status --assert-ready"))
        if post["boot_id"] != report["boot_id"] or post["issues"]:
            raise RuntimeError("post-install health changed")
        report["state"] = "installed-remote-capability-verified"
    except Exception as exc:
        report.update(state="failed", error=str(exc))
        if installed:
            try:
                step("rollback", f"cp -p {backup_runtime} /usr/local/bin/lynx-noobd; "
                     f"cp -p {backup_pulse} /usr/local/bin/lynx-flashlight-pulse; "
                     "rm -f /usr/local/share/lynx-tools/calls/lynx_flashlight_pulse.sh "
                     "/usr/local/share/lynx-tools/calls/lynx_flashlight_pulse.json; "
                     "rc-service lynx-noobd restart", timeout=45)
                report["state"] = "rolled-back"
            except Exception as rollback_exc:
                report["rollback_error"] = str(rollback_exc)
    (out / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"state": report["state"], "receipt": str(out / "result.json"),
                      "error": report.get("error")}))
    if report["state"] != "installed-remote-capability-verified":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
