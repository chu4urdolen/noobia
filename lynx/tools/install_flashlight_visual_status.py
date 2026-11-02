#!/usr/bin/env python3
"""Publish Noob's visual flashlight confirmation in Lynx's shared inventory."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from lynx_wifi_v19_contact import ssh_command

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "tools/lynx_hardware.py"
RECORD = ROOT / "tools/flashlight-visual-confirmation.json"
TARGET = "/usr/local/bin/lynx_hardware.py"
MARKER = "/var/lib/lynx-hardware/flashlight-visual.json"
BACKUP = TARGET + ".before-flashlight-visual"
OLD = "df1e8eb6c7fb467e962a525cb43063c16c7aa5e44089d1ef83f44e3a7bb1afaa"
STAGE = "/run/lynx/flashlight-visual-install-v2"


def main():
    os.umask(0o077)
    out = ROOT / "logs" / f"flashlight-visual-install-{time.time_ns()}"
    out.mkdir(mode=0o700)
    report = {"state": "starting", "boot_partition_writes": False,
              "module_loads": False, "led_actuation": False, "steps": []}

    def step(name, command, payload=None, timeout=20):
        argv = ssh_command("192.168.100.107", command)
        argv[-2:-2] = ["-p", "2222"]
        result = subprocess.run(argv, input=payload, capture_output=True,
                                timeout=timeout)
        (out / (name + ".stdout")).write_bytes(result.stdout)
        (out / (name + ".stderr")).write_bytes(result.stderr)
        report["steps"].append({"name": name, "exit": result.returncode})
        if result.returncode:
            raise RuntimeError(name + " failed; see receipt")
        return result.stdout.decode(errors="replace").strip()

    installed = False
    try:
        health = json.loads(step("health_before", "/usr/local/bin/lynx-status --assert-ready"))
        report["boot_id"] = health["boot_id"]
        if health["issues"] or health["battery"]["capacity_percent"] < 25:
            raise RuntimeError("health gate failed")
        if step("old_hash", f"sha256sum {TARGET} | cut -c1-64") != OLD:
            raise RuntimeError("installed hardware backend changed")
        step("preconditions", "set -eu; test -L /sys/bus/i2c/devices/6-0063/driver; "
             "test -c /dev/flashlight; grep -q '^lm3642_22823 ' /proc/modules; "
             f"test ! -e {MARKER}; rc-service lynx-noobd status")
        previous_backup = step("backup_state", f"if test -e {BACKUP}; then "
                               f"sha256sum {BACKUP} | cut -c1-64; else echo absent; fi")
        if previous_backup not in ("absent", OLD):
            raise RuntimeError("unexpected rollback copy")
        record = json.loads(RECORD.read_text())
        if (record.get("confirmed") is not True or record.get("device") != "CPH2493" or
                record.get("chip") != "lm3642_22823"):
            raise RuntimeError("visual confirmation record invalid")
        step("stage_dir", f"mkdir -m 700 {STAGE}")
        for label, source in (("backend", BACKEND), ("record", RECORD)):
            data = source.read_bytes()
            digest = hashlib.sha256(data).hexdigest()
            temp = f"{STAGE}/{source.name}"
            step("stage_" + label, f"cat > {temp}", data)
            if step("hash_" + label, f"sha256sum {temp} | cut -c1-64") != digest:
                raise RuntimeError("staged checksum mismatch: " + label)
        step("syntax", f"python3 -m py_compile {STAGE}/{BACKEND.name}; "
             f"python3 -m json.tool {STAGE}/{RECORD.name} >/dev/null")
        step("backup", f"if test ! -e {BACKUP}; then cp -p {TARGET} {BACKUP}; fi; "
             "mkdir -p /var/lib/lynx-hardware; "
             "chmod 700 /var/lib/lynx-hardware")
        installed = True
        step("install", f"cp {STAGE}/{BACKEND.name} {TARGET}.new; chmod 755 {TARGET}.new; "
             f"mv {TARGET}.new {TARGET}; cp {STAGE}/{RECORD.name} {MARKER}.new; "
             f"chmod 600 {MARKER}.new; mv {MARKER}.new {MARKER}")
        local = json.loads(step("local", "/usr/local/bin/lynx-hardware status flashlight"))
        if not local["validated"] or not local["interface_ready"]:
            raise RuntimeError("local inventory did not validate flashlight")
        step("restart", "rc-service lynx-noobd restart", timeout=35)
        remote = None
        for attempt in range(12):
            remote = subprocess.run(["python3", str(ROOT / "tools/lynx_noobctl.py"),
                                     "CALL", "FLASH_STATUS"], capture_output=True,
                                    text=True, timeout=12)
            report["nrp"] = remote.stdout.strip()
            report["nrp_attempts"] = attempt + 1
            if (not remote.returncode and "value=1" in remote.stdout and
                    "validated=1" in remote.stdout):
                break
            time.sleep(0.5)
        if remote.returncode or "value=1" not in remote.stdout or "validated=1" not in remote.stdout:
            raise RuntimeError("remote inventory did not validate flashlight")
        after = json.loads(step("health_after", "/usr/local/bin/lynx-status --assert-ready"))
        if after["boot_id"] != report["boot_id"] or after["issues"]:
            raise RuntimeError("post-install health changed")
        report["state"] = "installed-and-verified"
    except Exception as exc:
        report.update(state="failed", error=str(exc))
        if installed:
            try:
                step("rollback", f"cp -p {BACKUP} {TARGET}; rm -f {MARKER}; "
                     "rc-service lynx-noobd restart", timeout=35)
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
