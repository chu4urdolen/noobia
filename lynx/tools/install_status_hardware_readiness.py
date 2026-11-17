#!/usr/bin/env python3
"""Install Lynx's evidence-based hardware rows without a boot image change."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from lynx_wifi_v19_contact import ssh_command

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "tools/lynx_drm_dmabuf_pattern.c"
TARGET = "/usr/local/bin/lynx-portrait-display"
KERNEL = "5.10.149-android12-9-o-g311738fbb5a8"


def ssh(command, data=None, timeout=35):
    args = ssh_command("192.168.100.107", command)
    args[-2:-2] = ["-p", "2222"]
    return subprocess.run(args, input=data, capture_output=True, timeout=timeout)


def main():
    os.umask(0o077)
    out = ROOT / "logs" / f"status-hardware-{time.time_ns()}"
    out.mkdir(mode=0o700)
    report = {"state": "starting", "boot_partition_writes": False,
              "kernel_modules_loaded": False, "steps": []}

    def step(name, command, data=None, timeout=35):
        result = ssh(command, data, timeout)
        (out / (name + ".stdout")).write_bytes(result.stdout)
        (out / (name + ".stderr")).write_bytes(result.stderr)
        report["steps"].append({"name": name, "exit": result.returncode})
        if result.returncode:
            raise RuntimeError(f"{name} failed; see receipt streams")
        return result.stdout.decode(errors="replace").strip()

    source = SOURCE.read_bytes()
    digest = hashlib.sha256(source).hexdigest()
    temporary = "/var/lib/lynx-devroot/tmp/lynx-status-hardware.c"
    candidate = "/var/lib/lynx-devroot/tmp/lynx-status-hardware"
    backup = TARGET + ".before-camera-media-correction"
    installed = False
    try:
        identity = step("identity", "uname -r; cat /proc/sys/kernel/random/boot_id").splitlines()
        if len(identity) != 2 or identity[0] != KERNEL:
            raise RuntimeError("unexpected kernel or boot identity")
        report["boot_id"] = identity[1]
        health = json.loads(step("pre_health", "/usr/local/bin/lynx-status --assert-ready"))
        if (health["boot_id"] != identity[1] or health["issues"] or
                health["battery"]["capacity_percent"] < 25 or
                health["battery"]["temperature_mC"] >= 35000 or
                health["thermal"]["max_mC"] >= 45000):
            raise RuntimeError("health gate failed")
        report["old_sha256"] = step("old_hash", f"sha256sum {TARGET} | cut -c1-64")
        step("stage_source", f"cat > {temporary}", source, timeout=60)
        if step("source_hash", f"sha256sum {temporary} | cut -c1-64") != digest:
            raise RuntimeError("source transfer hash mismatch")
        step("compile", "chroot /var/lib/lynx-devroot /usr/bin/gcc -std=c11 "
             "-O2 -Wall -Wextra -Werror -I/usr/include/libdrm "
             "/tmp/lynx-status-hardware.c -ldrm -l:libz.so.1 "
             "-o /tmp/lynx-status-hardware", timeout=60)
        step("touch_test", candidate + " --self-test-touch")
        step("keys_test", candidate + " --self-test-console-keys")
        step("preview", candidate + " --preview-page status /run/lynx/status-hardware.ppm")
        preview = step("preview_hash", "sha256sum /run/lynx/status-hardware.ppm | cut -c1-64")
        report["preview_sha256"] = preview
        report["new_sha256"] = step("new_hash", f"sha256sum {candidate} | cut -c1-64")
        step("backup", f"set -eu; test ! -e {backup}; cp -p {TARGET} {backup}; "
             f"test \"$(sha256sum {backup} | cut -c1-64)\" = {report['old_sha256']}")
        step("install", f"set -eu; cp {candidate} {TARGET}.new; chmod 755 {TARGET}.new; "
             f"mv {TARGET}.new {TARGET}; "
             f"test \"$(sha256sum {TARGET} | cut -c1-64)\" = {report['new_sha256']}")
        installed = True
        step("restart_display", "rc-service lynx-display restart", timeout=50)
        step("post_health", "/usr/local/bin/lynx-status --assert-ready")
        step("display_status", "rc-service lynx-display status")
        report["state"] = "installed-and-running"
    except Exception as exc:
        report.update(state="failed", error=str(exc))
        if installed:
            try:
                step("rollback", f"cp -p {backup} {TARGET}.rollback; "
                     f"mv {TARGET}.rollback {TARGET}; rc-service lynx-display restart", timeout=50)
                report["state"] = "rolled-back"
            except Exception as rollback_exc:
                report["rollback_error"] = str(rollback_exc)
    report["finished_ns"] = time.time_ns()
    receipt = out / "result.json"
    receipt.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"state": report["state"], "receipt": str(receipt)}))
    if report["state"] != "installed-and-running":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
