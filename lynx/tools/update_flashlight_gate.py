#!/usr/bin/env python3
"""Install the charging-aware flashlight pulse gate with exact rollback."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from lynx_wifi_v19_contact import ssh_command

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "tools/lynx_flashlight_pulse.py"
TARGET = "/usr/local/bin/lynx-flashlight-pulse"
OLD = "fb6208703c81585430107db52b593c99a6921f6ca8fc21ce757654ba42bdcee9"
BACKUP = TARGET + ".before-charging-aware-gate"


def main():
    os.umask(0o077)
    out = ROOT / "logs" / f"flashlight-gate-{time.time_ns()}"
    out.mkdir(mode=0o700)
    result = {"state": "starting", "boot_partition_writes": False,
              "modules_loaded": False, "steps": []}

    def step(name, command, payload=None):
        argv = ssh_command("192.168.100.107", command)
        argv[-2:-2] = ["-p", "2222"]
        call = subprocess.run(argv, input=payload, capture_output=True, timeout=22)
        (out / (name + ".stdout")).write_bytes(call.stdout)
        (out / (name + ".stderr")).write_bytes(call.stderr)
        result["steps"].append({"name": name, "exit": call.returncode})
        if call.returncode:
            raise RuntimeError(name + " failed; see receipt")
        return call.stdout.decode(errors="replace").strip()

    installed = False
    try:
        before = json.loads(step("health_before", "/usr/local/bin/lynx-status --assert-ready"))
        result["boot_id"] = before["boot_id"]
        if before["issues"] or before["battery"]["capacity_percent"] < 25:
            raise RuntimeError("health gate failed")
        if step("old_hash", f"sha256sum {TARGET} | cut -c1-64") != OLD:
            raise RuntimeError("unexpected old pulse tool")
        data = SOURCE.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        temp = TARGET + ".new"
        step("stage", f"cat > {temp}", data)
        if step("new_hash", f"sha256sum {temp} | cut -c1-64") != digest:
            raise RuntimeError("transfer checksum mismatch")
        step("syntax", f"python3 -m py_compile {temp}")
        step("backup", f"test ! -e {BACKUP}; cp -p {TARGET} {BACKUP}")
        step("install", f"chmod 755 {temp}; mv {temp} {TARGET}")
        installed = True
        if step("installed_hash", f"sha256sum {TARGET} | cut -c1-64") != digest:
            raise RuntimeError("installed checksum mismatch")
        after = json.loads(step("health_after", "/usr/local/bin/lynx-status --assert-ready"))
        if after["boot_id"] != before["boot_id"] or after["issues"]:
            raise RuntimeError("post-install health changed")
        result["state"] = "installed-no-light-command"
    except Exception as exc:
        result.update(state="failed", error=str(exc))
        if installed:
            try:
                step("rollback", f"cp -p {BACKUP} {TARGET}")
                result["state"] = "rolled-back"
            except Exception as rollback_exc:
                result["rollback_error"] = str(rollback_exc)
    (out / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"state": result["state"], "receipt": str(out / "result.json"),
                      "error": result.get("error")}))
    if result["state"] != "installed-no-light-command":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
