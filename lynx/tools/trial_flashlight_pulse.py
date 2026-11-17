#!/usr/bin/env python3
"""Stage and run one bounded flashlight pulse on the verified V53 boot."""

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
BOOT = "c047455271828cf9bfa90984eea121d8ede8754f6297fc06f33f1e99fb23c75e"


def main():
    os.umask(0o077)
    out = ROOT / "logs" / f"flashlight-pulse-{time.time_ns()}"
    out.mkdir(mode=0o700)
    report = {"state": "starting", "boot_partition_writes": False,
              "modules_unloaded": False, "steps": []}

    def step(name, command, data=None, timeout=20):
        args = ssh_command("192.168.100.107", command)
        args[-2:-2] = ["-p", "2222"]
        result = subprocess.run(args, input=data, capture_output=True, timeout=timeout)
        (out / f"{name}.stdout").write_bytes(result.stdout)
        (out / f"{name}.stderr").write_bytes(result.stderr)
        report["steps"].append({"name": name, "exit": result.returncode})
        if result.returncode:
            raise RuntimeError(f"{name} failed; see receipt")
        return result.stdout.decode(errors="replace").strip()

    try:
        boot = step("boot_hash", "sha256sum /dev/sdc39 | cut -c1-64", timeout=30)
        if boot != BOOT:
            raise RuntimeError("unexpected boot image")
        report["boot_sha256"] = boot
        report["health_before"] = json.loads(step("health_before", "/usr/local/bin/lynx-status --assert-ready"))
        data = SOURCE.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        step("stage", f"cat > {TARGET}.new", data)
        if step("stage_hash", f"sha256sum {TARGET}.new | cut -c1-64") != digest:
            raise RuntimeError("transfer hash mismatch")
        step("install", f"chmod 755 {TARGET}.new && mv {TARGET}.new {TARGET}")
        step("syntax", f"python3 -m py_compile {TARGET}")
        result = step("pulse", f"{TARGET} --duration-ms 100", timeout=15)
        report["pulse"] = json.loads(result)
        if not report["pulse"].get("off_verified"):
            raise RuntimeError("OFF was not verified")
        report["health_after"] = json.loads(step("health_after", "/usr/local/bin/lynx-status --assert-ready"))
        if report["health_after"]["boot_id"] != report["health_before"]["boot_id"]:
            raise RuntimeError("boot changed")
        report["state"] = "pulse-commanded-off-verified-awaiting-visual-confirmation"
    except Exception as exc:
        report.update(state="failed", error=str(exc))
    (out / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"state": report["state"], "receipt": str(out / "result.json"),
                      "error": report.get("error")}))
    if report["state"] == "failed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
